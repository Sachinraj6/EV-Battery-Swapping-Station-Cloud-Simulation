# EV Battery-Swapping Station Cloud Simulation

[![Infrastructure](https://img.shields.io/badge/IaC-Terraform-623CE4?logo=terraform)](https://www.terraform.io/)
[![Cloud](https://img.shields.io/badge/Cloud-AWS-FF9900?logo=amazon-aws)](https://aws.amazon.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> A production-quality learning project demonstrating event-driven serverless architecture on AWS for IoT telemetry processing.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Cost Estimation](#cost-estimation)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

This project simulates a cloud infrastructure for managing EV (Electric Vehicle) battery-swapping stations. It demonstrates:

- **Event-driven serverless architecture** using AWS Lambda, IoT Core, and API Gateway
- **Infrastructure as Code** with Terraform for reproducible deployments
- **Real-time data processing** from IoT devices to storage and APIs
- **Cost-optimized cloud design** using managed AWS services
- **DevOps best practices** with CI/CD validation and comprehensive documentation

### What This Is

✅ A **learning prototype** for cloud architecture and DevOps concepts  
✅ A **demonstration** of AWS serverless services integration  
✅ A **foundation** for building production IoT systems  
✅ An **interview-ready** project with defensible design decisions

### What This Is NOT

❌ Production-ready without additional hardening  
❌ Suitable for safety-critical systems  
❌ A complete EV management system  
❌ Optimized for 10,000+ concurrent devices

See [docs/limitations.md](docs/limitations.md) for complete details.

---

## Architecture

```
MQTT Telemetry     AWS IoT Core      Lambda           DynamoDB
(Simulated) ────► (Message Broker) ──► (Processing) ──► (Current State)
                                      │
                                      └──► S3 (Historical Data)
                                      
                                      Lambda         API Gateway
External Clients ◄──── API Response ◄─ (Query) ◄─── (REST API)
```

### Data Flow

1. **Telemetry Generation**: Python simulator publishes MQTT messages to IoT Core
2. **Message Routing**: IoT Rule triggers Lambda function for each message
3. **Processing**: Lambda validates, transforms, and stores data
4. **Storage**: 
   - Latest state → DynamoDB (fast queries)
   - Raw archive → S3 (cheap long-term storage)
5. **API Access**: REST API via API Gateway + Lambda serves current data

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **IoT Ingestion** | AWS IoT Core | MQTT message broker |
| **Compute** | AWS Lambda | Serverless event processing |
| **Storage** | DynamoDB + S3 | Fast queries + archival |
| **API** | API Gateway | REST endpoints |
| **IaC** | Terraform | Infrastructure automation |
| **CI/CD** | GitHub Actions | Code validation |
| **Monitoring** | CloudWatch | Logs and metrics |

---

## Features

### Implemented

- ✅ **MQTT Telemetry Ingestion** - Real-time data from simulated stations
- ✅ **Dual-Write Pattern** - Optimized storage for different access patterns
- ✅ **REST API** - Query current station status
- ✅ **Infrastructure as Code** - Complete Terraform configuration
- ✅ **CI/CD Validation** - Automated linting and validation
- ✅ **Cost Optimization** - S3 lifecycle policies, on-demand billing
- ✅ **Comprehensive Logging** - CloudWatch integration
- ✅ **Security** - IAM least-privilege, encryption at rest

### Planned Enhancements

- 🔲 Real-time WebSocket dashboard
- 🔲 Historical analytics with Athena
- 🔲 API authentication (Cognito)
- 🔲 Multi-region deployment
- 🔲 Comprehensive test suite

---

## Prerequisites

Before you begin, ensure you have:

- **AWS Account** with admin access ([Create account](https://aws.amazon.com/free/))
- **AWS CLI** configured ([Installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html))
- **Terraform** ≥ 1.0 ([Download](https://www.terraform.io/downloads))
- **Python** 3.11+ ([Download](https://www.python.org/downloads/))
- **Git** ([Download](https://git-scm.com/downloads))

### Verify Installation

```bash
aws --version       # Should show AWS CLI version
terraform --version # Should show ≥ 1.0
python --version    # Should show 3.11+
git --version       # Should show git version
```

---

## Quick Start

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd ev-battery-swap-cloud
```

### 2. Deploy Infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply  # Type 'yes' when prompted

# Save outputs
terraform output > ../deployment-info.txt
```

### 3. Create IoT Certificates

```bash
cd ../certs

# Create device certificate
aws iot create-keys-and-certificate \
  --set-as-active \
  --certificate-pem-outfile device.pem.crt \
  --public-key-outfile public.pem.key \
  --private-key-outfile private.pem.key

# Save the certificateArn from output!

# Download Root CA
curl -o AmazonRootCA1.pem \
  https://www.amazontrust.com/repository/AmazonRootCA1.pem

# Attach policy (replace <CERT_ARN> and <POLICY_NAME>)
aws iot attach-policy \
  --policy-name <POLICY_NAME> \
  --target <CERT_ARN>
```

### 4. Configure Simulator

```bash
cd ../simulation

# Edit station_simulator.py
# Update these values:
# - IOT_ENDPOINT = "<your-iot-endpoint>"  # From terraform output
# - IOT_CERT_PATH = "../certs/device.pem.crt"
# - IOT_KEY_PATH = "../certs/private.pem.key"
```

### 5. Run Simulator

```bash
# Install dependencies
pip install -r requirements.txt

# Run simulator (10 stations, 5-second interval)
python station_simulator.py --num-stations 10 --interval 5

# Expected output:
# INFO - Created 10 simulated stations
# INFO - Connecting to AWS IoT Core...
# INFO - Published telemetry for station-01: batteries=12, temp=25.3°C
```

### 6. Test API

```bash
# Get API URL from Terraform
cd ../terraform
API_URL=$(terraform output -raw api_gateway_invoke_url)

# List all stations
curl "${API_URL}/stations" | jq .

# Get specific station
curl "${API_URL}/stations/station-01" | jq .
```

### 7. Monitor

- **CloudWatch Logs**: AWS Console → CloudWatch → Log Groups
- **DynamoDB**: AWS Console → DynamoDB → Tables → `ev-swap-dev-stations`
- **S3**: AWS Console → S3 → Buckets → `ev-swap-dev-telemetry-*`

---

## Project Structure

```
ev-battery-swap-cloud/
├── README.md
├── .gitignore
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── iam.tf
│   ├── dynamodb.tf
│   ├── s3.tf
│   ├── lambda.tf
│   ├── iot.tf
│   └── api_gateway.tf
├── lambda/
│   ├── telemetry_handler.py
│   ├── api_handler.py
│   └── requirements.txt
├── simulation/
│   ├── station_simulator.py
│   └── requirements.txt
├── .github/
│   └── workflows/
│       └── validate.yml
└── docs/
    ├── architecture.md
    └── limitations.md
```

```
ev-battery-swap-cloud/
├── README.md                          # This file
├── .gitignore                         # Security-focused ignore rules
│
├── terraform/                         # Infrastructure as Code
│   ├── main.tf                       # Provider and core config
│   ├── variables.tf                  # Input variables
│   ├── outputs.tf                    # Output values
│   ├── iam.tf                        # IAM roles and policies
│   ├── dynamodb.tf                   # NoSQL database
│   ├── s3.tf                         # Object storage
│   ├── lambda.tf                     # Serverless functions
│   ├── iot.tf                        # IoT Core configuration
│   └── api_gateway.tf                # REST API
│
├── lambda/                            # Lambda function code
│   ├── telemetry_handler.py          # Process IoT messages
│   ├── api_handler.py                # Handle API requests
│   └── requirements.txt              # Python dependencies
│
├── simulation/                        # Station simulator
│   ├── station_simulator.py          # Generate telemetry
│   └── requirements.txt              # Simulator dependencies
│
├── .github/                           # CI/CD workflows
│   └── workflows/
│       └── validate.yml              # Automated validation
│
├── docs/                              # Documentation
│   ├── architecture.md               # Design decisions
│   ├── limitations.md                # Honest constraints
│   └── setup-guide.md                # Step-by-step setup
│
└── certs/                             # IoT certificates (git-ignored)
    ├── device.pem.crt                # Device certificate
    ├── private.pem.key               # Private key (SECRET!)
    └── AmazonRootCA1.pem             # Root CA
```

---

## Documentation

### Complete Guides

- 📖 **[Setup Guide](docs/setup-guide.md)** - Detailed deployment instructions
- 🏗️ **[Architecture Documentation](docs/architecture.md)** - Design decisions and patterns
- ⚠️ **[Limitations](docs/limitations.md)** - Honest assessment of constraints

### Code Documentation

Every file contains extensive inline comments explaining:
- **WHY** design decisions were made
- **WHAT** each component does
- **HOW** services integrate
- **WHEN** to use alternatives

Example from `lambda/telemetry_handler.py`:
```python
# WHY: DynamoDB doesn't support Python float type
# Must use Decimal for numeric values with decimals
# Without this, Lambda would crash on DynamoDB write
def convert_floats_to_decimal(data):
    ...
```

---

## Cost Estimation

### Expected Monthly Costs

**For 20 stations, 5-second telemetry interval:**

| Service | Cost | Notes |
|---------|------|-------|
| **IoT Core** | ~$5 | Message ingestion (100K messages/month) |
| **Lambda** | ~$2 | Compute time (200K invocations) |
| **DynamoDB** | ~$1 | On-demand reads/writes |
| **S3** | ~$1 | Storage + requests |
| **API Gateway** | ~$1 | Light API usage |
| **CloudWatch** | ~$2 | Logs (7-day retention) |
| **Data Transfer** | ~$1 | Inter-service communication |
| **Total** | **~$12-15/month** | |

### Cost Optimization Tips

✅ **Implemented**:
- S3 lifecycle policies (Glacier after 90 days)
- CloudWatch log retention (7 days)
- On-demand DynamoDB billing
- Regional API Gateway

🔮 **Future Optimizations**:
- DynamoDB reserved capacity (save 50%+)
- CloudFront caching for API
- Lambda reserved concurrency

### Monitor Costs

```bash
# View current month costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost

# Set budget alert (recommended)
# AWS Console → Billing → Budgets → Create Budget
# Threshold: $20/month
```

---

## Limitations

### Key Constraints

This is a **learning prototype**. Important limitations:

❌ **Not production-ready** - No HA, no formal SLAs  
❌ **Scale limit** - Designed for 10-50 stations (not 10,000)  
❌ **No real-time** - Eventual consistency, no latency SLOs  
❌ **Basic security** - No API authentication, basic IAM  
❌ **No advanced analytics** - No ML, no real-time dashboards  
❌ **Limited testing** - Manual testing only  

### What Production Would Add

✅ Multi-region deployment  
✅ Comprehensive test suite (unit, integration, load)  
✅ API authentication (Cognito)  
✅ Advanced monitoring (X-Ray, custom metrics)  
✅ Security hardening (WAF, Secrets Manager)  
✅ Formal CI/CD with staged deployments  

**See [docs/limitations.md](docs/limitations.md) for complete details.**

---

## Troubleshooting

### Common Issues

<details>
<summary><b>Simulator Can't Connect to IoT Core</b></summary>

**Symptoms**: `Connection failed` or certificate errors

**Solutions**:
```bash
# Verify IoT endpoint
aws iot describe-endpoint --endpoint-type iot:Data-ATS

# Check certificate status
aws iot describe-certificate --certificate-id <cert-id>

# Verify policy attached
aws iot list-attached-policies --target <cert-arn>

# Test certificate files exist
ls -la certs/
```
</details>

<details>
<summary><b>No Data in DynamoDB</b></summary>

**Symptoms**: Table empty after running simulator

**Solutions**:
```bash
# Check Lambda logs
aws logs tail /aws/lambda/ev-swap-dev-telemetry-handler --follow

# Verify IoT Rule enabled
aws iot get-topic-rule --rule-name ev_swap_dev_telemetry_rule

# Test Lambda directly
aws lambda invoke \
  --function-name ev-swap-dev-telemetry-handler \
  --payload '{"station_id":"test","battery_available":10,"timestamp":"2024-01-15T14:00:00Z"}' \
  response.json
```
</details>

<details>
<summary><b>API Returns 500/502 Error</b></summary>

**Symptoms**: Internal server error from API

**Solutions**:
```bash
# Check API handler logs
aws logs tail /aws/lambda/ev-swap-dev-api-handler --follow

# Test Lambda directly
aws lambda invoke \
  --function-name ev-swap-dev-api-handler \
  --payload '{"httpMethod":"GET","path":"/stations"}' \
  response.json
```
</details>

### Get Help

- 📚 [AWS Documentation](https://docs.aws.amazon.com)
- 🔧 [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws)
- 💬 [AWS Forums](https://forums.aws.amazon.com)
- ❓ [Stack Overflow](https://stackoverflow.com/questions/tagged/aws)

---

## Cleanup

### Destroy All Infrastructure

```bash
cd terraform

# Preview what will be deleted
terraform plan -destroy

# Destroy (WARNING: Deletes all data!)
terraform destroy

# Type 'yes' to confirm
```

### Delete IoT Certificates

```bash
# Deactivate certificate
aws iot update-certificate \
  --certificate-id <cert-id> \
  --new-status INACTIVE

# Delete certificate
aws iot delete-certificate \
  --certificate-id <cert-id>
```

**⚠️ Warning**: This permanently deletes all data!

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

### Code Standards

- All Terraform: `terraform fmt -recursive`
- All Python: Follow PEP 8 (use `black` formatter)
- Add inline comments explaining **WHY**, not just **WHAT**
- Update documentation for significant changes

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## Acknowledgments

Built for learning cloud architecture and DevOps practices.

**Technologies Used**:
- [AWS](https://aws.amazon.com) - Cloud platform
- [Terraform](https://www.terraform.io) - Infrastructure as Code
- [Python](https://www.python.org) - Application code
- [AWS IoT SDK](https://github.com/aws/aws-iot-device-sdk-python-v2) - MQTT client

---

## Author

Sachinraj

---



**Q: Why DynamoDB over RDS?**
> "I chose DynamoDB because we have a simple key-value access pattern (station_id → state) with no complex queries or joins. DynamoDB provides single-digit millisecond latency, serverless scaling, and on-demand billing that's cost-effective for unpredictable IoT traffic. If we needed relational queries like 'stations with low battery in California', RDS would be more appropriate."

**Q: Why Lambda instead of EC2?**
> "This is an event-driven workload triggered by MQTT messages. Lambda auto-scales from 0 to 1000 concurrent executions without managing servers, and we only pay for actual execution time. An EC2 instance would need to run 24/7 even during idle periods, costing significantly more for this intermittent load pattern."

**Q: How would you scale to 10,000 stations?**
> "The architecture scales horizontally: IoT Core and S3 handle millions automatically, Lambda would need increased concurrency limits, and DynamoDB would switch to provisioned capacity for cost efficiency. The main bottleneck would be Lambda concurrent executions - I'd request a limit increase from AWS support. Costs would scale linearly to approximately $200/month."

**Q: What about data consistency?**
> "We use eventual consistency which is acceptable for IoT monitoring. DynamoDB writes are atomic per item. The dual-write to S3 and DynamoDB could have partial failures, but for this use case, occasional missing S3 archives are acceptable since the current state in DynamoDB is always updated atomically. For critical systems, I'd use DynamoDB transactions or single-write with DynamoDB Streams triggering S3 archival."

---

<p align="center">
  <b>⭐ Star this repo if you find it helpful!</b>
</p>

<p align="center">
  Made with ☕ for learning cloud architecture
</p>
