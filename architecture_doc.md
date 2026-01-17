# Architecture Documentation

## System Overview

This document provides detailed architectural information about the EV Battery-Swapping Station Cloud Simulation project.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SIMULATED STATIONS                            │
│  (Python script generates telemetry every 5 seconds)                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ MQTT/TLS (Port 8883)
                            │ Topic: ev/station/{id}/telemetry
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS IOT CORE                                 │
│  • MQTT Message Broker                                              │
│  • Device Authentication (X.509 certificates)                       │
│  • Message Routing (IoT Rules)                                      │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ Trigger (IoT Rule)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LAMBDA: Telemetry Handler                        │
│  • Validate incoming data                                           │
│  • Process telemetry                                                │
│  • Dual-write pattern                                               │
└─────────┬───────────────────────────────────────────┬───────────────┘
          │                                           │
          │ Write latest state                        │ Archive raw data
          ▼                                           ▼
┌──────────────────────┐                   ┌─────────────────────────┐
│    DYNAMODB TABLE    │                   │      S3 BUCKET          │
│  • station_id (PK)   │                   │  • Raw JSON files       │
│  • Current state     │                   │  • Date-partitioned     │
│  • Fast queries      │                   │  • Lifecycle policies   │
│  • On-demand billing │                   │  • Glacier archival     │
└──────────┬───────────┘                   └─────────────────────────┘
           │
           │ Read operations
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LAMBDA: API Handler                             │
│  • Query DynamoDB                                                   │
│  • Format responses                                                 │
│  • CORS headers                                                     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            │ Invocation
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API GATEWAY                                    │
│  • REST API Endpoints:                                              │
│    - GET /stations                                                  │
│    - GET /stations/{station_id}                                     │
│  • Rate limiting                                                    │
│  • Request validation                                               │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTPS
                            │
                            ▼
                      External Clients
                (curl, browser, mobile apps)

                            │
                            │ All services log to
                            ▼
                    ┌───────────────────┐
                    │  CLOUDWATCH LOGS  │
                    │  • Lambda logs    │
                    │  • API logs       │
                    │  • IoT logs       │
                    │  • Metrics        │
                    └───────────────────┘
```

---

## Data Flow

### Telemetry Ingestion Flow

1. **Station Simulator** generates telemetry:
   ```json
   {
     "station_id": "station-01",
     "battery_available": 12,
     "battery_charging": 4,
     "temperature": 28.5,
     "humidity": 42.0,
     "status": "operational",
     "timestamp": "2024-01-15T14:23:45Z"
   }
   ```

2. **MQTT Connection**:
   - Simulator connects to IoT Core using X.509 certificate
   - Publishes to topic: `ev/station/station-01/telemetry`
   - Uses QoS 1 (at-least-once delivery)

3. **IoT Rule Processing**:
   - SQL filter: `SELECT * FROM 'ev/station/+/telemetry'`
   - Matches any station_id (+ wildcard)
   - Triggers Lambda asynchronously

4. **Lambda Processing**:
   - Validates payload schema
   - Writes to DynamoDB (latest state)
   - Archives to S3 (historical data)
   - Logs to CloudWatch

5. **Storage**:
   - **DynamoDB**: Single item per station (upsert)
   - **S3**: New file per message at `telemetry/year=2024/month=01/day=15/station-01_timestamp_uuid.json`

### API Query Flow

1. **Client Request**:
   ```bash
   GET https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/stations
   ```

2. **API Gateway**:
   - Validates request format
   - Checks rate limits
   - Adds CORS headers
   - Invokes Lambda (POST internally)

3. **Lambda Execution**:
   - Routes based on path and method
   - Queries DynamoDB
   - Converts Decimal to float
   - Formats JSON response

4. **Response**:
   ```json
   {
     "count": 10,
     "stations": [
       {
         "station_id": "station-01",
         "battery_available": 12,
         "temperature": 28.5,
         ...
       }
     ]
   }
   ```

---

## Design Decisions

### Why These AWS Services?

| Service | Why Chosen | Alternatives Considered |
|---------|------------|------------------------|
| **IoT Core** | Purpose-built for MQTT devices, handles millions of connections | EC2 with Mosquitto broker (too complex), HTTP API (less suitable for IoT) |
| **Lambda** | Event-driven, auto-scales, pay-per-use | EC2 (overkill for simple processing), ECS (too complex) |
| **DynamoDB** | Single-digit millisecond latency, serverless scaling | RDS (too complex for key-value), ElastiCache (adds complexity) |
| **S3** | Cheap storage, infinite scalability, lifecycle policies | EBS volumes (expensive), DynamoDB (too expensive for archival) |
| **API Gateway** | Managed REST API, integrates with Lambda | ALB + Lambda (more to manage), EC2 web server (not serverless) |

### Architecture Patterns

#### 1. Dual-Write Pattern (Lambda → DynamoDB + S3)

**Why**: Different access patterns require different storage

```python
# Write to both simultaneously
dynamodb_success = store_in_dynamodb(event)
s3_success = archive_to_s3(event)
```

**Trade-offs**:
- ✅ Optimized for each use case (fast queries + cheap archival)
- ✅ Data redundancy
- ❌ Two write operations (slightly slower)
- ❌ Potential inconsistency (partial failure)

**Alternatives Considered**:
- S3 → Lambda → DynamoDB (S3 events): Adds latency
- DynamoDB Streams → S3: Adds complexity
- Single storage (DynamoDB only): Too expensive for historical data

#### 2. AWS Proxy Integration (API Gateway + Lambda)

**Why**: Simplifies request/response handling

```hcl
type = "AWS_PROXY"
```

**Benefits**:
- Lambda receives full HTTP request
- No request/response transformation templates
- Easier to debug

**Trade-offs**:
- ✅ Less boilerplate
- ✅ Lambda has full control
- ❌ Lambda must format HTTP response correctly
- ❌ Can't use API Gateway request validation

#### 3. On-Demand Billing (DynamoDB)

**Why**: Unpredictable traffic, prototype use case

```hcl
billing_mode = "PAY_PER_REQUEST"
```

**When to Use**:
- Unpredictable traffic patterns
- Spiky workloads
- Development/testing
- Low-traffic applications

**When to Switch to Provisioned**:
- Steady, predictable traffic
- High sustained throughput
- Cost optimization (>$100/month DynamoDB bill)

#### 4. Date-Partitioned S3 Keys

**Why**: Enables efficient querying with Athena/EMR

```
s3://bucket/telemetry/year=2024/month=01/day=15/file.json
```

**Benefits**:
- Athena queries only scan needed partitions
- Lifecycle policies work on folders
- Hive-style partitioning standard
- Easy to delete old data by date

---

## Scalability Analysis

### Current Scale (Prototype)

- **Stations**: 10-50
- **Message Rate**: 1 message/5 seconds = 12/minute per station
- **Total Messages**: 600/minute (10 stations) to 3,000/minute (50 stations)
- **Data Volume**: ~1KB per message = 36KB/minute to 180KB/minute

### Bottlenecks and Limits

| Component | Current Limit | Breaking Point | Mitigation |
|-----------|--------------|----------------|------------|
| **IoT Core** | 500,000 msg/sec | Never (at our scale) | N/A |
| **Lambda (Concurrent)** | 1,000 default | >1,000 stations @ 5s interval | Request limit increase |
| **DynamoDB (On-Demand)** | 40,000 RCU/WCU | Very unlikely | Switch to provisioned |
| **API Gateway** | 10,000 req/sec | High API traffic | Use CloudFront caching |
| **S3** | 5,500 PUT/sec/prefix | >27,500 stations @ 5s | Use random prefixes |

### Scaling to 1,000 Stations

**Changes Required**:
1. **IoT Core**: No changes (easily handles)
2. **Lambda**: Request concurrent execution limit increase (to 200)
3. **DynamoDB**: Consider provisioned capacity (~50 WCU, ~20 RCU)
4. **S3**: Use random UUID prefixes to distribute load
5. **API Gateway**: Add CloudFront for caching

**Estimated Cost at 1,000 Stations**:
- IoT Core: $100/month
- Lambda: $50/month
- DynamoDB: $30/month (provisioned)
- S3: $20/month
- **Total**: ~$200/month

---

## Security Architecture

### Defense in Depth

```
Layer 1: Network (HTTPS/TLS only)
   ↓
Layer 2: Authentication (X.509 certificates for IoT, IAM for API)
   ↓
Layer 3: Authorization (IoT policies, IAM roles)
   ↓
Layer 4: Encryption (In-transit and at-rest)
   ↓
Layer 5: Monitoring (CloudWatch logs and alarms)
```

### IAM Permission Model

**Principle**: Least Privilege (minimum permissions needed)

```
IoT Rule → Lambda Telemetry
  ↓ Can only:
    - Write to specific DynamoDB table
    - Write to specific S3 bucket
    - Write to CloudWatch logs

API Gateway → Lambda API
  ↓ Can only:
    - Read from DynamoDB table
    - Write to CloudWatch logs
```

### Encryption

| Data State | Encryption Method | Key Management |
|------------|-------------------|----------------|
| IoT in-transit | TLS 1.2+ | AWS Certificate Manager |
| DynamoDB at-rest | AES-256 | AWS-managed |
| S3 at-rest | SSE-S3 | AWS-managed |
| API Gateway in-transit | TLS 1.2+ | AWS Certificate Manager |
| CloudWatch Logs | AES-256 | AWS-managed (optional KMS) |

### Secrets Management

**Current** (Prototype):
- Certificates stored locally
- No secrets in code

**Production**:
- AWS Secrets Manager for API keys
- IoT certificate management via IoT Core
- Rotate credentials regularly
- Use AWS Systems Manager Parameter Store

---

## Cost Optimization Strategies

### Implemented

1. **S3 Lifecycle Policies**: Move old data to Glacier after 90 days
2. **CloudWatch Log Retention**: Only 7 days (not infinite)
3. **On-Demand DynamoDB**: Pay only for what you use
4. **Lambda Memory Sizing**: 256MB (enough, not wasteful)
5. **Regional API Gateway**: Cheaper than Edge

### Future Optimizations

1. **DynamoDB Reserved Capacity**: Save 50%+ if traffic is predictable
2. **S3 Intelligent Tiering**: Auto-optimize storage class
3. **Lambda Reserved Concurrency**: Reduce cold starts (costs more)
4. **Savings Plans**: Commit to usage for discount
5. **CloudWatch Log Insights**: Replace custom log analysis tools

### Cost Monitoring

```bash
# View costs by service
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE

# Set budget alert
aws budgets create-budget \
  --account-id 123456789012 \
  --budget '{"BudgetName":"EV-Swap-Monthly","BudgetLimit":{"Amount":"50","Unit":"USD"},...}'
```

---

## Failure Modes and Recovery

| Failure | Impact | Detection | Recovery |
|---------|--------|-----------|----------|
| **Lambda timeout** | Message lost | CloudWatch alarm on errors | Increase timeout, optimize code |
| **DynamoDB throttling** | Writes fail | CloudWatch alarm on throttles | Increase capacity, use exponential backoff |
| **IoT connection drop** | Simulator disconnects | Connection logs | Auto-reconnect in SDK |
| **S3 write failure** | Archive lost (DynamoDB OK) | Lambda logs | Retry with exponential backoff |
| **API Gateway 5xx** | Client gets error | CloudWatch alarm | Check Lambda logs, may need scale |

### Disaster Recovery

**RPO (Recovery Point Objective)**: ~5 seconds (last telemetry message)
**RTO (Recovery Time Objective)**: <5 minutes (redeploy Lambda)

**Backup Strategy**:
- DynamoDB: Point-in-time recovery (35 days)
- S3: Versioning enabled, object lock (optional)
- Infrastructure: Terraform state in version control

**Recovery Procedure**:
1. Identify failed component via CloudWatch
2. Check recent deployments (Terraform, Lambda updates)
3. Roll back if needed: `terraform apply` previous version
4. Restore DynamoDB from backup if data corruption
5. Verify with smoke tests

---

## Monitoring and Observability

### Key Metrics

| Metric | Threshold | Action |
|--------|-----------|--------|
| Lambda error rate | >1% | Investigate logs |
| Lambda duration | >5s avg | Optimize code |
| DynamoDB throttles | >0 | Increase capacity |
| API Gateway 5xx | >5 in 5min | Check Lambda |
| API Gateway latency | >1s | Optimize queries |

### Log Aggregation

All services → CloudWatch Logs → (Optional) → Elasticsearch/Datadog

```bash
# Tail Lambda logs
aws logs tail /aws/lambda/ev-swap-dev-telemetry-handler --follow

# Query logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/ev-swap-dev-telemetry-handler \
  --filter-pattern "ERROR"
```

### Distributed Tracing

**X-Ray Integration**:
- Enabled in Lambda (prod only to save cost)
- Traces request through API Gateway → Lambda → DynamoDB
- Identifies bottlenecks

---

## Future Enhancements

1. **Real-time Dashboard**: WebSocket API + React frontend
2. **Predictive Analytics**: ML model for battery demand forecasting
3. **Multi-Region**: Deploy in us-east-1 and eu-west-1
4. **GraphQL API**: Replace REST with AppSync
5. **Event Sourcing**: DynamoDB Streams → Kinesis → Analytics
6. **Mobile App**: React Native app using API
7. **Admin Portal**: Cognito authentication + S3 static site

---

## Interview Talking Points

### Question: "Why DynamoDB over RDS?"

**Answer**: 
"For this use case, DynamoDB was the better choice because:
1. We have a simple key-value access pattern (station_id → state)
2. No complex queries, joins, or transactions needed
3. Serverless scaling without managing database instances
4. Single-digit millisecond latency even at scale
5. On-demand billing works well for unpredictable IoT traffic

However, if we needed complex queries like 'stations with low battery in California', RDS with SQL would be more appropriate."

### Question: "How would you handle 10x traffic?"

**Answer**:
"The architecture is designed to scale horizontally:
1. IoT Core and S3 handle millions of requests automatically
2. Lambda auto-scales (would request higher concurrency limit)
3. DynamoDB would move to provisioned capacity for cost efficiency
4. API Gateway handles 10k req/sec by default
5. Main bottleneck would be Lambda concurrent executions - mitigated by requesting limit increase

Cost would scale linearly, approximately 10x current cost."

### Question: "What about data consistency?"

**Answer**:
"We use eventual consistency which is acceptable for this IoT use case:
- DynamoDB writes are atomic per item
- Dual-write to S3 and DynamoDB could have partial failures
- For this monitoring use case, occasional missing S3 archive is acceptable
- Current state in DynamoDB is always updated atomically

For critical systems requiring strong consistency, I'd use:
- DynamoDB transactions for atomic multi-item writes
- Or change to single-write with DynamoDB Streams → S3"