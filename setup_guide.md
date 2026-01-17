# Complete Setup Guide

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] AWS Account with admin access
- [ ] AWS CLI installed and configured (`aws --version`)
- [ ] Terraform installed (`terraform --version >= 1.0`)
- [ ] Python 3.11+ installed (`python --version`)
- [ ] Git installed
- [ ] Text editor (VS Code recommended)
- [ ] Basic understanding of AWS services

---

## Step 1: Clone and Setup Repository

```bash
# Clone the repository
git clone <your-repo-url>
cd ev-battery-swap-cloud

# Create directory for IoT certificates
mkdir -p certs

# Verify structure
tree -L 2
# Should show:
# ├── README.md
# ├── lambda/
# ├── simulation/
# ├── terraform/
# └── certs/  (empty for now)
```

---

## Step 2: Configure AWS Credentials

### Option A: AWS CLI Configuration

```bash
# Configure AWS credentials
aws configure

# You'll be prompted for:
# AWS Access Key ID: [Your access key]
# AWS Secret Access Key: [Your secret key]
# Default region name: us-east-1
# Default output format: json

# Verify configuration
aws sts get-caller-identity
# Should return your AWS account ID and ARN
```

### Option B: Environment Variables

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

### Option C: IAM Role (if running on EC2)

```bash
# No configuration needed if instance has IAM role
# Verify with:
aws sts get-caller-identity
```

---

## Step 3: Initialize Terraform

```bash
# Navigate to terraform directory
cd terraform

# Initialize Terraform (downloads AWS provider)
terraform init

# Expected output:
# Terraform has been successfully initialized!

# Format Terraform files (ensures consistent style)
terraform fmt -recursive

# Validate configuration
terraform validate

# Expected output:
# Success! The configuration is valid.
```

---

## Step 4: Review Terraform Plan

```bash
# Generate execution plan
terraform plan

# This shows what will be created:
# - DynamoDB table
# - S3 bucket
# - Lambda functions (2)
# - IoT Core rule
# - API Gateway
# - IAM roles and policies
# - CloudWatch log groups

# Review carefully before proceeding!
```

**⚠️ Important**: Review the plan output carefully. Look for:
- Resource names match expected pattern
- No unexpected deletions (should be all creates)
- Estimated costs (should show "Plan: X to add")

---

## Step 5: Deploy Infrastructure

```bash
# Apply Terraform configuration
terraform apply

# You'll be prompted: "Do you want to perform these actions?"
# Type: yes

# Deployment takes 2-5 minutes
# Watch for errors in red
# Success message: "Apply complete! Resources: X added"

# IMPORTANT: Save these outputs
terraform output > ../deployment-outputs.txt

# View specific outputs
terraform output api_gateway_invoke_url
terraform output iot_endpoint_address
```

**💾 Save Important Information**:
```bash
# These values are needed later
API_URL=$(terraform output -raw api_gateway_invoke_url)
IOT_ENDPOINT=$(terraform output -raw iot_endpoint_address)

echo "API URL: $API_URL"
echo "IoT Endpoint: $IOT_ENDPOINT"
```

---

## Step 6: Create IoT Certificates

IoT devices need X.509 certificates for authentication.

### Create Certificate via AWS CLI

```bash
# Navigate to certs directory
cd ../certs

# Create certificate and keys
aws iot create-keys-and-certificate \
  --set-as-active \
  --certificate-pem-outfile device.pem.crt \
  --public-key-outfile public.pem.key \
  --private-key-outfile private.pem.key \
  --region us-east-1

# Save certificate ARN from output
# Example output:
# {
#   "certificateArn": "arn:aws:iot:us-east-1:123456789012:cert/abc123...",
#   "certificateId": "abc123...",
#   ...
# }

# Save the certificateArn - you'll need it!
CERT_ARN="arn:aws:iot:us-east-1:123456789012:cert/abc123..."

# Download Amazon Root CA certificate
curl -o AmazonRootCA1.pem \
  https://www.amazontrust.com/repository/AmazonRootCA1.pem

# Verify files created
ls -la
# Should show:
# - device.pem.crt
# - private.pem.key
# - public.pem.key
# - AmazonRootCA1.pem
```

### Attach IoT Policy to Certificate

```bash
# Get policy name from Terraform
cd ../terraform
POLICY_NAME=$(terraform output -raw iot_policy_name)

# Attach policy to certificate
aws iot attach-policy \
  --policy-name $POLICY_NAME \
  --target $CERT_ARN

# Verify attachment
aws iot list-attached-policies --target $CERT_ARN
```

**⚠️ Security Note**: 
- Never commit certificates to git
- Keep `private.pem.key` secret
- Add `certs/` to `.gitignore` (already done)

---

## Step 7: Configure Simulator

```bash
# Navigate to simulation directory
cd ../simulation

# Edit station_simulator.py
nano station_simulator.py  # or use VS Code

# Update these lines (around line 30):
IOT_ENDPOINT = "YOUR_IOT_ENDPOINT_HERE"  # From Step 5
IOT_CERT_PATH = "../certs/device.pem.crt"
IOT_KEY_PATH = "../certs/private.pem.key"
IOT_CA_PATH = "../certs/AmazonRootCA1.pem"

# Save and exit (Ctrl+X, Y, Enter in nano)
```

**Quick Find-Replace**:
```bash
# Get IoT endpoint
cd ../terraform
IOT_ENDPOINT=$(terraform output -raw iot_endpoint_address)

# Update simulator (macOS/Linux)
cd ../simulation
sed -i.bak "s/your-iot-endpoint.iot.us-east-1.amazonaws.com/$IOT_ENDPOINT/" station_simulator.py

# Verify change
grep "IOT_ENDPOINT" station_simulator.py
```

---

## Step 8: Install Python Dependencies

### For Simulator

```bash
cd simulation

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
pip list
# Should show: awsiotsdk, awscrt, colorama
```

### For Lambda (Local Testing)

```bash
cd ../lambda

# Create separate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify
pip list
# Should show: boto3, botocore
```

---

## Step 9: Test the System

### 9.1: Test API (Before Telemetry)

```bash
# Get API URL
cd ../terraform
API_URL=$(terraform output -raw api_gateway_invoke_url)

# Test list stations endpoint (should be empty initially)
curl "${API_URL}/stations"

# Expected response:
# {"count": 0, "stations": []}

# Test specific station (should return 404)
curl "${API_URL}/stations/station-01"

# Expected response:
# {"error": "Not found", "message": "Station station-01 not found"}
```

### 9.2: Run Simulator

```bash
# Navigate to simulation directory
cd ../simulation

# Make sure virtual environment is activated
source venv/bin/activate

# Run simulator with 10 stations, 5-second interval
python station_simulator.py --num-stations 10 --interval 5

# Expected output:
# 2024-01-15 14:30:00 - INFO - Created 10 simulated stations
# 2024-01-15 14:30:00 - INFO - Connecting to AWS IoT Core...
# 2024-01-15 14:30:01 - INFO - Successfully connected
# 2024-01-15 14:30:01 - INFO - Published telemetry for station-01: batteries=12, temp=25.3°C
# ...

# Let it run for 30-60 seconds to generate data
# Stop with Ctrl+C
```

### 9.3: Verify Data in DynamoDB

```bash
# In a new terminal window
cd terraform
TABLE_NAME=$(terraform output -raw dynamodb_table_name)

# Scan DynamoDB table
aws dynamodb scan --table-name $TABLE_NAME

# Should show station data:
# {
#   "Items": [
#     {
#       "station_id": {"S": "station-01"},
#       "battery_available": {"N": "12"},
#       ...
#     }
#   ]
# }

# Count items
aws dynamodb scan --table-name $TABLE_NAME --select COUNT
```

### 9.4: Verify Data in S3

```bash
# Get bucket name
S3_BUCKET=$(terraform output -raw s3_bucket_name)

# List recent telemetry files
aws s3 ls s3://$S3_BUCKET/telemetry/ --recursive | tail -20

# Download a sample file
aws s3 cp s3://$S3_BUCKET/telemetry/year=2024/month=01/day=15/station-01_20240115_143045_abc123.json sample.json

# View contents
cat sample.json | jq .
```

### 9.5: Test API (After Telemetry)

```bash
# Test list stations (should now have data)
curl "${API_URL}/stations" | jq .

# Expected response:
# {
#   "count": 10,
#   "stations": [
#     {
#       "station_id": "station-01",
#       "battery_available": 12,
#       ...
#     }
#   ]
# }

# Test specific station
curl "${API_URL}/stations/station-01" | jq .

# Expected response:
# {
#   "station": {
#     "station_id": "station-01",
#     "battery_available": 12,
#     "temperature": 28.5,
#     ...
#   }
# }
```

---

## Step 10: Monitor in AWS Console

### CloudWatch Logs

1. Open AWS Console → CloudWatch → Log Groups
2. Find these log groups:
   - `/aws/lambda/ev-swap-dev-telemetry-handler`
   - `/aws/lambda/ev-swap-dev-api-handler`
   - `/aws/apigateway/ev-swap-dev-stations-api`

3. Click on a log group → View log streams
4. Click on latest stream → See log entries

**Useful Log Insights Query**:
```sql
# In CloudWatch → Insights
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 20
```

### DynamoDB Console

1. AWS Console → DynamoDB → Tables
2. Click on `ev-swap-dev-stations`
3. Click "Explore items" → See station data

### S3 Console

1. AWS Console → S3 → Buckets
2. Click on `ev-swap-dev-telemetry-*` bucket
3. Navigate: telemetry → year=2024 → month=01 → day=15
4. Download and view JSON files

### API Gateway Console

1. AWS Console → API Gateway → APIs
2. Click on `ev-swap-dev-stations-api`
3. Click "Stages" → dev → See invoke URL
4. Click "Logs" → See request logs

---

## Step 11: Load Testing (Optional)

### Simple Load Test

```bash
# Install hey (HTTP load testing tool)
# macOS:
brew install hey

# Linux:
wget https://hey-release.s3.us-east-1.amazonaws.com/hey_linux_amd64
chmod +x hey_linux_amd64

# Run load test (100 requests, 10 concurrent)
hey -n 100 -c 10 "${API_URL}/stations"

# Review results:
# - Requests/sec
# - Response time distribution
# - Error rate
```

### Simulator Load Test

```bash
# Run multiple simulator instances
# Terminal 1:
python station_simulator.py --num-stations 10 --interval 5

# Terminal 2:
python station_simulator.py --num-stations 10 --interval 5

# Terminal 3:
python station_simulator.py --num-stations 10 --interval 5

# Watch Lambda metrics in CloudWatch
# Should see increased invocation count
```

---

## Step 12: Cost Monitoring

### View Current Costs

```bash
# Get cost for last 30 days
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '30 days ago' +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE

# View by resource tags
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '30 days ago' +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=TAG,Key=Project
```

### Set Budget Alert

```bash
# Create budget (manual via console easier)
# AWS Console → Billing → Budgets → Create budget
# Set monthly budget: $20
# Alert threshold: 80% ($16)
# Email notification: your@email.com
```

---

## Troubleshooting Guide

### Issue: Simulator Can't Connect to IoT

**Symptoms**: `Connection failed` or `Certificate error`

**Checks**:
```bash
# 1. Verify endpoint
aws iot describe-endpoint --endpoint-type iot:Data-ATS

# 2. Verify certificate is active
aws iot describe-certificate --certificate-id <cert-id>
# Should show: "status": "ACTIVE"

# 3. Verify policy attached
aws iot list-attached-policies --target <cert-arn>

# 4. Check certificate files exist
ls -la certs/
# Should have: device.pem.crt, private.pem.key, AmazonRootCA1.pem

# 5. Test with mosquitto (if installed)
mosquitto_pub \
  --cafile certs/AmazonRootCA1.pem \
  --cert certs/device.pem.crt \
  --key certs/private.pem.key \
  -h <iot-endpoint> \
  -p 8883 \
  -t 'test/topic' \
  -m 'hello' \
  --insecure
```

### Issue: No Data in DynamoDB

**Symptoms**: DynamoDB table empty after running simulator

**Checks**:
```bash
# 1. Check Lambda logs for errors
aws logs tail /aws/lambda/ev-swap-dev-telemetry-handler --follow

# 2. Verify IoT Rule is active
aws iot get-topic-rule --rule-name ev_swap_dev_telemetry_rule

# 3. Check Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=ev-swap-dev-telemetry-handler \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# 4. Test Lambda directly
aws lambda invoke \
  --function-name ev-swap-dev-telemetry-handler \
  --payload '{"station_id":"test","battery_available":10,"timestamp":"2024-01-15T14:00:00Z"}' \
  response.json
cat response.json
```

### Issue: API Returns 502/500 Error

**Symptoms**: `curl` returns `{"message": "Internal server error"}`

**Checks**:
```bash
# 1. Check Lambda logs
aws logs tail /aws/lambda/ev-swap-dev-api-handler --follow

# 2. Verify Lambda exists and is deployed
aws lambda get-function --function-name ev-swap-dev-api-handler

# 3. Test Lambda directly
aws lambda invoke \
  --function-name ev-swap-dev-api-handler \
  --payload '{"httpMethod":"GET","path":"/stations"}' \
  response.json
cat response.json

# 4. Check API Gateway integration
aws apigateway get-integration \
  --rest-api-id <api-id> \
  --resource-id <resource-id> \
  --http-method GET
```

### Issue: High AWS Costs

**Immediate Actions**:
```bash
# 1. Stop simulator
# Press Ctrl+C in simulator terminal

# 2. Check current costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '7 days ago' +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity DAILY \
  --metrics BlendedCost

# 3. Check Lambda invocations (main cost driver)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum

# 4. Destroy infrastructure if needed
cd terraform
terraform destroy  # Type 'yes' to confirm
```

---

## Cleanup / Teardown

### Complete Cleanup

```bash
# 1. Stop simulator
# Press Ctrl+C if running

# 2. Navigate to terraform directory
cd terraform

# 3. Destroy all infrastructure
terraform destroy

# You'll be prompted to confirm
# Review what will be deleted
# Type: yes

# 4. Verify deletion
aws dynamodb list-tables | grep ev-swap
# Should return nothing

# 5. Delete IoT certificate
aws iot update-certificate \
  --certificate-id <cert-id> \
  --new-status INACTIVE

aws iot delete-certificate \
  --certificate-id <cert-id>

# 6. Clean local files (optional)
rm -rf .terraform/
rm terraform.tfstate*
rm -rf ../certs/*
```

**⚠️ Warning**: This deletes ALL data permanently!

### Partial Cleanup (Keep Infrastructure)

```bash
# Just clear DynamoDB table
TABLE_NAME=$(terraform output -raw dynamodb_table_name)
aws dynamodb scan --table-name $TABLE_NAME | \
  jq -r '.Items[].station_id.S' | \
  xargs -I {} aws dynamodb delete-item \
    --table-name $TABLE_NAME \
    --key '{"station_id":{"S":"{}"}}'

# Clear S3 bucket
S3_BUCKET=$(terraform output -raw s3_bucket_name)
aws s3 rm s3://$S3_BUCKET/ --recursive
```

---

## Next Steps

### Extend the Project

1. **Add Real-Time Dashboard**: Use WebSocket API for live updates
2. **Implement Analytics**: Use Athena to query S3 data
3. **Add Authentication**: Implement Cognito for API security
4. **Multi-Region**: Deploy in multiple AWS regions
5. **Add Tests**: Write unit and integration tests

### Learn More

- AWS IoT Core documentation
- Lambda best practices
- DynamoDB design patterns
- API Gateway optimization
- Terraform AWS provider docs

---

## Getting Help

- **AWS Documentation**: https://docs.aws.amazon.com
- **Terraform AWS Provider**: https://registry.terraform.io/providers/hashicorp/aws
- **AWS Forums**: https://forums.aws.amazon.com
- **Stack Overflow**: Tag questions with `aws`, `terraform`, `aws-lambda`

---

## Success Checklist

- [ ] Infrastructure deployed successfully
- [ ] IoT certificates created and attached
- [ ] Simulator connects and publishes data
- [ ] Data appears in DynamoDB
- [ ] Data archived to S3
- [ ] API returns station data
- [ ] CloudWatch logs show activity
- [ ] No errors in Lambda functions
- [ ] Costs within expected range (<$15/month)
- [ ] Can explain architecture to others

**Congratulations! Your EV Battery-Swap Cloud Infrastructure is running!** 🎉