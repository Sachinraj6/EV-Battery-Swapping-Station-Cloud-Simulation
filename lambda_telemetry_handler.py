"""
lambda/telemetry_handler.py

PURPOSE: Process incoming telemetry from EV battery swap stations

WHAT THIS FUNCTION DOES:
1. Receives telemetry messages from AWS IoT Core
2. Validates the data structure
3. Stores latest state in DynamoDB (fast lookups)
4. Archives raw data to S3 (historical analysis)
5. Logs important events for monitoring

WHY LAMBDA:
- Event-driven: Runs only when telemetry arrives (cost-efficient)
- Auto-scales: Handles 1 or 1000 messages without manual intervention
- Serverless: No servers to patch or maintain

TRIGGERED BY: AWS IoT Core Rule when MQTT messages arrive

EXPECTED INPUT (from IoT Core):
{
    "station_id": "station-01",
    "battery_available": 12,
    "battery_charging": 4,
    "temperature": 32.5,
    "humidity": 45.2,
    "status": "operational",
    "timestamp": "2024-01-15T14:23:45Z"
}
"""

import json
import boto3
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Set up logging - goes to CloudWatch Logs
# WHY: Debugging Lambda requires good logs (no SSH access)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS service clients
# WHY: Reusing clients across invocations improves performance
# IMPORTANT: Initialize outside handler for Lambda container reuse
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Get configuration from environment variables
# WHY: Makes Lambda configurable without code changes
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Get DynamoDB table reference
# WHY: Reuse table reference for better performance
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def validate_telemetry(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate incoming telemetry data structure
    
    WHY THIS FUNCTION:
    - Prevents bad data from corrupting database
    - Returns clear error messages for debugging
    - Fails fast (don't waste time processing invalid data)
    
    Args:
        data: Dictionary containing telemetry data
        
    Returns:
        tuple: (is_valid: bool, error_message: Optional[str])
    """
    
    # List of required fields
    # WHY: These fields are essential for system operation
    required_fields = [
        'station_id',
        'battery_available',
        'timestamp'
    ]
    
    # Check for missing required fields
    for field in required_fields:
        if field not in data:
            error_msg = f"Missing required field: {field}"
            logger.error(error_msg)
            return False, error_msg
    
    # Validate station_id format
    # WHY: Consistent naming prevents database issues
    station_id = data.get('station_id')
    if not isinstance(station_id, str) or not station_id.strip():
        return False, "station_id must be a non-empty string"
    
    # Validate battery_available is a number
    # WHY: Prevents type errors in database and analytics
    battery_available = data.get('battery_available')
    if not isinstance(battery_available, (int, float)) or battery_available < 0:
        return False, "battery_available must be a non-negative number"
    
    # Validate timestamp format
    # WHY: Ensures time-series data is properly ordered
    try:
        datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return False, "timestamp must be valid ISO-8601 format"
    
    # All validations passed
    return True, None


def convert_floats_to_decimal(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert float values to Decimal for DynamoDB
    
    WHY THIS FUNCTION:
    - DynamoDB doesn't support Python float type
    - Must use Decimal for numeric values with decimals
    - Without this, Lambda would crash on DynamoDB write
    
    Args:
        data: Dictionary potentially containing floats
        
    Returns:
        Dictionary with floats converted to Decimal
    """
    
    converted = {}
    for key, value in data.items():
        if isinstance(value, float):
            # Convert float to Decimal
            # WHY: DynamoDB requires Decimal for precision
            converted[key] = Decimal(str(value))
        elif isinstance(value, dict):
            # Recursively convert nested dictionaries
            converted[key] = convert_floats_to_decimal(value)
        elif isinstance(value, list):
            # Convert lists of floats
            converted[key] = [
                Decimal(str(item)) if isinstance(item, float) else item
                for item in value
            ]
        else:
            converted[key] = value
    
    return converted


def store_in_dynamodb(data: Dict[str, Any]) -> bool:
    """
    Store latest station state in DynamoDB
    
    WHY THIS FUNCTION:
    - Provides fast (single-digit ms) lookups of current state
    - Overwrites previous state (we only need latest)
    - Enables API to serve real-time data
    
    Args:
        data: Validated telemetry data
        
    Returns:
        bool: True if successful, False otherwise
    """
    
    try:
        # Convert floats to Decimal for DynamoDB
        data_to_store = convert_floats_to_decimal(data)
        
        # Add metadata
        # WHY: Track when data was processed by Lambda
        data_to_store['lambda_processed_at'] = datetime.utcnow().isoformat()
        
        # Write to DynamoDB
        # WHY: PutItem creates or replaces item (upsert operation)
        # PERFORMANCE: Typically completes in <10ms
        response = table.put_item(Item=data_to_store)
        
        logger.info(
            f"Stored state for station {data['station_id']} in DynamoDB",
            extra={'station_id': data['station_id']}
        )
        
        return True
        
    except Exception as e:
        # Log error but don't crash - we can still save to S3
        logger.error(
            f"Failed to store in DynamoDB: {str(e)}",
            extra={'station_id': data.get('station_id'), 'error': str(e)}
        )
        return False


def archive_to_s3(data: Dict[str, Any]) -> bool:
    """
    Archive raw telemetry to S3 for historical analysis
    
    WHY THIS FUNCTION:
    - S3 is cheap storage for rarely-accessed data
    - Enables future analytics without overloading DynamoDB
    - Provides data durability (11 9's - 99.999999999%)
    
    OBJECT KEY STRUCTURE:
    telemetry/year=YYYY/month=MM/day=DD/station-XX_YYYYMMDD_HHMMSS_UUID.json
    
    WHY THIS STRUCTURE:
    - Partitioned by date for efficient querying (Athena, EMR)
    - Includes timestamp for ordering
    - UUID prevents collisions if multiple messages same second
    
    Args:
        data: Validated telemetry data
        
    Returns:
        bool: True if successful, False otherwise
    """
    
    try:
        # Parse timestamp from telemetry
        timestamp = datetime.fromisoformat(
            data['timestamp'].replace('Z', '+00:00')
        )
        
        # Generate S3 key with date partitioning
        # WHY: Partitions make future queries faster and cheaper
        # EXAMPLE: telemetry/year=2024/month=01/day=15/station-01_20240115_143045_abc.json
        import uuid
        s3_key = (
            f"telemetry/"
            f"year={timestamp.year}/"
            f"month={timestamp.month:02d}/"
            f"day={timestamp.day:02d}/"
            f"{data['station_id']}_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.json"
        )
        
        # Convert to JSON string
        # WHY: S3 stores bytes, need to serialize Python dict
        json_data = json.dumps(data, indent=2, default=str)
        
        # Upload to S3
        # PERFORMANCE: Typically completes in <100ms for small objects
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=json_data,
            ContentType='application/json',
            # Metadata for object tagging
            Metadata={
                'station_id': data['station_id'],
                'ingestion_time': datetime.utcnow().isoformat()
            }
        )
        
        logger.info(
            f"Archived to S3: {s3_key}",
            extra={'station_id': data['station_id'], 's3_key': s3_key}
        )
        
        return True
        
    except Exception as e:
        # Log error and continue - S3 failure shouldn't stop DynamoDB write
        logger.error(
            f"Failed to archive to S3: {str(e)}",
            extra={'station_id': data.get('station_id'), 'error': str(e)}
        )
        return False


# ==============================================================================
# LAMBDA HANDLER (Entry Point)
# ==============================================================================

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda function handler
    
    INVOKED BY: AWS IoT Core Rule when MQTT message arrives
    
    EXECUTION MODEL:
    1. Lambda container starts (cold start ~1-2 seconds first time)
    2. Handler executes (typically <100ms for our logic)
    3. Container stays warm for ~5-15 minutes for reuse
    
    Args:
        event: Dictionary containing telemetry data from IoT Core
        context: Lambda context object (request ID, memory, timeout info)
        
    Returns:
        Dictionary with status code and message (for logging/debugging)
    """
    
    # Log the incoming event for debugging
    # WHY: Helps troubleshoot issues in CloudWatch Logs
    logger.info(
        f"Processing telemetry event",
        extra={
            'request_id': context.request_id,
            'function_name': context.function_name,
            'memory_limit_mb': context.memory_limit_in_mb
        }
    )
    
    try:
        # STEP 1: Validate incoming data
        # WHY: Fail fast on bad data, prevents downstream issues
        is_valid, error_message = validate_telemetry(event)
        
        if not is_valid:
            logger.error(f"Validation failed: {error_message}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Validation failed',
                    'message': error_message
                })
            }
        
        station_id = event['station_id']
        logger.info(f"Processing telemetry for station: {station_id}")
        
        # STEP 2: Store in DynamoDB (latest state)
        # WHY: DynamoDB first for fast API queries
        dynamodb_success = store_in_dynamodb(event)
        
        # STEP 3: Archive to S3 (historical data)
        # WHY: S3 for cheap long-term storage and analytics
        s3_success = archive_to_s3(event)
        
        # STEP 4: Determine overall success
        # LOGIC: Both operations should succeed, but partial success is OK
        if dynamodb_success and s3_success:
            status_code = 200
            message = "Telemetry processed successfully"
        elif dynamodb_success or s3_success:
            status_code = 207  # Multi-Status (partial success)
            message = "Telemetry partially processed"
            logger.warning(
                f"Partial success for {station_id}: "
                f"DynamoDB={dynamodb_success}, S3={s3_success}"
            )
        else:
            status_code = 500
            message = "Failed to process telemetry"
            logger.error(f"Complete failure for {station_id}")
        
        # STEP 5: Return response
        # NOTE: IoT Core doesn't use this response, but useful for testing
        return {
            'statusCode': status_code,
            'body': json.dumps({
                'message': message,
                'station_id': station_id,
                'dynamodb_success': dynamodb_success,
                's3_success': s3_success,
                'timestamp': datetime.utcnow().isoformat()
            })
        }
    
    except Exception as e:
        # Catch-all error handler
        # WHY: Ensures Lambda doesn't crash silently
        logger.error(
            f"Unexpected error in lambda_handler: {str(e)}",
            exc_info=True  # Includes full stack trace
        )
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


# ==============================================================================
# FOR LOCAL TESTING (Optional)
# ==============================================================================
# Uncomment to test locally without deploying to AWS
#
# if __name__ == "__main__":
#     # Mock event data
#     test_event = {
#         "station_id": "station-test-01",
#         "battery_available": 15,
#         "battery_charging": 3,
#         "temperature": 28.5,
#         "humidity": 42.0,
#         "status": "operational",
#         "timestamp": datetime.utcnow().isoformat() + "Z"
#     }
#     
#     # Mock context
#     class MockContext:
#         request_id = "test-request-123"
#         function_name = "telemetry_handler"
#         memory_limit_in_mb = 256
#     
#     # Call handler
#     result = lambda_handler(test_event, MockContext())
#     print(json.dumps(result, indent=2))