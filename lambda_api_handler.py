"""
lambda/api_handler.py

PURPOSE: Handle API Gateway requests for station data

WHAT THIS FUNCTION DOES:
1. Receives HTTP requests from API Gateway
2. Queries DynamoDB for current station state
3. Returns JSON response with proper HTTP codes

ENDPOINTS HANDLED:
- GET /stations - List all stations
- GET /stations/{station_id} - Get specific station details

WHY SEPARATE FROM TELEMETRY HANDLER:
- Different IAM permissions (read-only vs read-write)
- Different invocation pattern (HTTP vs IoT event)
- Easier to scale and monitor separately

TRIGGERED BY: API Gateway HTTP requests
"""

import json
import boto3
import os
import logging
from typing import Dict, Any, List
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Set up logging for CloudWatch
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
# WHY: Reuse client across Lambda invocations (container reuse)
dynamodb = boto3.resource('dynamodb')

# Get table name from environment variable
DYNAMODB_TABLE_NAME = os.environ['DYNAMODB_TABLE_NAME']
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def decimal_to_float(obj: Any) -> Any:
    """
    Convert Decimal objects to float for JSON serialization
    
    WHY THIS FUNCTION:
    - DynamoDB returns numbers as Decimal type
    - JSON doesn't support Decimal (only float/int)
    - Must convert before returning to API Gateway
    
    Args:
        obj: Object potentially containing Decimal values
        
    Returns:
        Object with Decimals converted to float
    """
    if isinstance(obj, Decimal):
        # Convert Decimal to float or int
        # WHY: Preserves integer values as int (not 12.0)
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        # Recursively convert dictionary values
        return {key: decimal_to_float(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        # Recursively convert list items
        return [decimal_to_float(item) for item in obj]
    else:
        return obj


def create_response(status_code: int, body: Any, headers: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Create standardized API Gateway response
    
    WHY THIS FUNCTION:
    - API Gateway requires specific response format
    - Ensures consistent CORS headers
    - Centralizes response structure
    
    Args:
        status_code: HTTP status code (200, 404, 500, etc.)
        body: Response data (will be JSON-serialized)
        headers: Optional additional headers
        
    Returns:
        Dictionary formatted for API Gateway
    """
    
    # Default headers
    # WHY: CORS allows browser-based clients to call API
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',  # CORS: Allow all origins
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    # Merge with custom headers if provided
    if headers:
        default_headers.update(headers)
    
    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body, default=str)  # default=str handles datetime
    }


def get_all_stations() -> List[Dict[str, Any]]:
    """
    Retrieve all stations from DynamoDB
    
    WHY SCAN OPERATION:
    - Need all items in table (no specific partition key)
    - Acceptable for small datasets (<100 stations)
    - For large datasets, would use pagination or GSI
    
    PERFORMANCE CONSIDERATION:
    - Scan reads entire table (can be slow/expensive)
    - OK for prototype with <100 stations
    - Production would cache this or use pagination
    
    Returns:
        List of station dictionaries
    """
    
    try:
        logger.info("Scanning DynamoDB for all stations")
        
        # Scan the table
        # WHY SCAN: No specific key, need all items
        # CAUTION: Scan reads entire table - expensive at scale
        response = table.scan()
        
        items = response.get('Items', [])
        
        # Handle pagination if more than 1MB of data
        # WHY: DynamoDB returns max 1MB per request
        while 'LastEvaluatedKey' in response:
            logger.info("Fetching next page of results")
            response = table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        logger.info(f"Retrieved {len(items)} stations")
        
        # Convert Decimal to float for JSON
        return [decimal_to_float(item) for item in items]
        
    except Exception as e:
        logger.error(f"Error scanning table: {str(e)}", exc_info=True)
        raise


def get_station_by_id(station_id: str) -> Dict[str, Any]:
    """
    Retrieve specific station by ID
    
    WHY GET_ITEM OPERATION:
    - Know exact partition key (station_id)
    - Single-item lookup is fast (<10ms)
    - More efficient than scanning
    
    Args:
        station_id: Unique identifier for station
        
    Returns:
        Station dictionary or None if not found
    """
    
    try:
        logger.info(f"Getting station: {station_id}")
        
        # Get item by partition key
        # WHY GET_ITEM: Fast, consistent read using primary key
        # PERFORMANCE: Typically <10ms
        response = table.get_item(
            Key={'station_id': station_id}
        )
        
        # Check if item exists
        # WHY: GetItem returns empty dict if item not found
        if 'Item' not in response:
            logger.warning(f"Station not found: {station_id}")
            return None
        
        # Convert Decimal to float for JSON
        return decimal_to_float(response['Item'])
        
    except Exception as e:
        logger.error(
            f"Error getting station {station_id}: {str(e)}",
            exc_info=True
        )
        raise


def handle_get_stations(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle GET /stations - list all stations
    
    ENDPOINT: GET /stations
    QUERY PARAMS: None (future: could add filtering, pagination)
    
    Args:
        event: API Gateway event
        
    Returns:
        API Gateway response with list of stations
    """
    
    try:
        # Get all stations from DynamoDB
        stations = get_all_stations()
        
        # Return success response
        return create_response(
            status_code=200,
            body={
                'count': len(stations),
                'stations': stations
            }
        )
        
    except Exception as e:
        logger.error(f"Error in handle_get_stations: {str(e)}", exc_info=True)
        return create_response(
            status_code=500,
            body={
                'error': 'Internal server error',
                'message': 'Failed to retrieve stations'
            }
        )


def handle_get_station_by_id(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle GET /stations/{station_id} - get specific station
    
    ENDPOINT: GET /stations/{station_id}
    PATH PARAMS: station_id (required)
    
    Args:
        event: API Gateway event containing station_id in path
        
    Returns:
        API Gateway response with station details or 404
    """
    
    try:
        # Extract station_id from path parameters
        # WHY: API Gateway puts path params in pathParameters dict
        path_params = event.get('pathParameters', {})
        station_id = path_params.get('station_id')
        
        # Validate station_id present
        if not station_id:
            return create_response(
                status_code=400,
                body={
                    'error': 'Bad request',
                    'message': 'station_id is required'
                }
            )
        
        # Get station from DynamoDB
        station = get_station_by_id(station_id)
        
        # Return 404 if station not found
        if station is None:
            return create_response(
                status_code=404,
                body={
                    'error': 'Not found',
                    'message': f'Station {station_id} not found'
                }
            )
        
        # Return station data
        return create_response(
            status_code=200,
            body={'station': station}
        )
        
    except Exception as e:
        logger.error(
            f"Error in handle_get_station_by_id: {str(e)}",
            exc_info=True
        )
        return create_response(
            status_code=500,
            body={
                'error': 'Internal server error',
                'message': 'Failed to retrieve station'
            }
        )


def handle_options(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle OPTIONS requests for CORS preflight
    
    WHY THIS FUNCTION:
    - Browsers send OPTIONS request before actual request (CORS preflight)
    - Must return allowed methods and headers
    - Required for browser-based API clients
    
    Args:
        event: API Gateway event
        
    Returns:
        200 response with CORS headers
    """
    
    return create_response(
        status_code=200,
        body={'message': 'CORS preflight response'}
    )


# ==============================================================================
# LAMBDA HANDLER (Entry Point)
# ==============================================================================

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda function handler for API requests
    
    INVOKED BY: API Gateway when HTTP request received
    
    ROUTING LOGIC:
    - GET /stations -> list all stations
    - GET /stations/{station_id} -> get specific station
    - OPTIONS * -> CORS preflight
    
    Args:
        event: API Gateway event with HTTP method, path, headers, etc.
        context: Lambda context object
        
    Returns:
        Dictionary formatted for API Gateway response
    """
    
    # Log request for debugging
    logger.info(
        f"API request received",
        extra={
            'http_method': event.get('httpMethod'),
            'path': event.get('path'),
            'request_id': context.request_id
        }
    )
    
    try:
        # Extract HTTP method and path
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
        # Handle OPTIONS for CORS preflight
        # WHY: Browsers send this before actual request
        if http_method == 'OPTIONS':
            return handle_options(event)
        
        # Route based on HTTP method and path
        # WHY: Single Lambda can handle multiple endpoints
        if http_method == 'GET':
            # GET /stations - list all
            if path == '/stations':
                return handle_get_stations(event)
            
            # GET /stations/{station_id} - get specific
            elif path.startswith('/stations/'):
                return handle_get_station_by_id(event)
            
            else:
                # Unknown path
                return create_response(
                    status_code=404,
                    body={
                        'error': 'Not found',
                        'message': f'Path {path} not found'
                    }
                )
        
        else:
            # Unsupported HTTP method
            return create_response(
                status_code=405,
                body={
                    'error': 'Method not allowed',
                    'message': f'Method {http_method} not supported'
                }
            )
    
    except Exception as e:
        # Catch-all error handler
        logger.error(
            f"Unexpected error in lambda_handler: {str(e)}",
            exc_info=True
        )
        
        return create_response(
            status_code=500,
            body={
                'error': 'Internal server error',
                'message': 'An unexpected error occurred'
            }
        )


# ==============================================================================
# FOR LOCAL TESTING (Optional)
# ==============================================================================
# Uncomment to test locally
#
# if __name__ == "__main__":
#     # Mock event for GET /stations
#     test_event_list = {
#         'httpMethod': 'GET',
#         'path': '/stations',
#         'pathParameters': None
#     }
#     
#     # Mock event for GET /stations/station-01
#     test_event_single = {
#         'httpMethod': 'GET',
#         'path': '/stations/station-01',
#         'pathParameters': {'station_id': 'station-01'}
#     }
#     
#     # Mock context
#     class MockContext:
#         request_id = "test-request-456"
#         function_name = "api_handler"
#     
#     # Test list endpoint
#     result = lambda_handler(test_event_list, MockContext())
#     print("List stations:", json.dumps(result, indent=2))
#     
#     # Test single station endpoint
#     result = lambda_handler(test_event_single, MockContext())
#     print("Get station:", json.dumps(result, indent=2))