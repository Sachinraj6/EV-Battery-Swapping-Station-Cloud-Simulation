"""
simulation/station_simulator.py

PURPOSE: Simulate EV battery swap stations sending telemetry to AWS IoT Core

WHAT THIS SCRIPT DOES:
1. Creates simulated station data (battery levels, temperature, etc.)
2. Connects to AWS IoT Core via MQTT protocol
3. Publishes telemetry messages every few seconds
4. Simulates realistic operational patterns

WHY THIS EXISTS:
- Test the cloud infrastructure without real hardware
- Demonstrate event-driven data flow
- Validate end-to-end system integration

MQTT PROTOCOL:
- Lightweight pub/sub messaging protocol
- Standard for IoT devices (low bandwidth, reliable)
- AWS IoT Core acts as MQTT broker

USAGE:
    python station_simulator.py --num-stations 10 --interval 5

REQUIREMENTS:
- AWS IoT Core endpoint configured
- IoT Thing certificates downloaded
- MQTT client library installed
"""

import json
import time
import random
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
import sys

# Try to import AWS IoT SDK
# WHY: This library handles MQTT connection to AWS IoT Core
try:
    from awsiot import mqtt_connection_builder
    from awscrt import mqtt
except ImportError:
    print("ERROR: AWS IoT SDK not installed")
    print("Install with: pip install awsiotsdk")
    sys.exit(1)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS IoT Core configuration
# NOTE: Replace these with your actual AWS IoT values
# FIND THESE: AWS Console > IoT Core > Settings
IOT_ENDPOINT = "your-iot-endpoint.iot.us-east-1.amazonaws.com"  # Replace!
IOT_CERT_PATH = "../certs/device.pem.crt"     # Path to device certificate
IOT_KEY_PATH = "../certs/private.pem.key"     # Path to private key
IOT_CA_PATH = "../certs/AmazonRootCA1.pem"    # Path to Amazon root CA

# MQTT topic pattern
# WHY: Matches IoT Rule filter in Terraform
TOPIC_PREFIX = "ev/station"

# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class StationState:
    """
    Represents the current state of a battery swap station
    
    WHY DATACLASS:
    - Clean, type-safe data structure
    - Auto-generates __init__, __repr__, etc.
    - Easy conversion to/from dictionaries
    
    FIELDS EXPLAINED:
    - station_id: Unique identifier (e.g., "station-01")
    - battery_available: Batteries ready for swapping
    - battery_charging: Batteries currently charging
    - temperature: Ambient temperature in Celsius
    - humidity: Relative humidity percentage
    - status: operational | maintenance | offline
    - total_swaps_today: Counter reset at midnight
    - last_swap_time: ISO-8601 timestamp of last swap
    """
    
    station_id: str
    battery_available: int
    battery_charging: int
    temperature: float
    humidity: float
    status: str
    total_swaps_today: int
    last_swap_time: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class BatterySwapStation:
    """
    Simulates a single battery swap station's behavior
    
    WHY THIS CLASS:
    - Encapsulates station logic and state
    - Simulates realistic operational patterns
    - Makes code modular and testable
    
    SIMULATION LOGIC:
    - Batteries slowly charge over time
    - Random battery swaps occur
    - Temperature fluctuates realistically
    - Status can change to maintenance mode
    """
    
    def __init__(self, station_id: str):
        """
        Initialize a new station simulator
        
        Args:
            station_id: Unique identifier for this station
        """
        self.station_id = station_id
        
        # Initialize battery counts
        # WHY THESE VALUES: Realistic for a small station
        self.battery_available = random.randint(8, 15)  # 8-15 ready batteries
        self.battery_charging = random.randint(2, 6)    # 2-6 charging
        
        # Initialize environmental sensors
        # WHY THESE RANGES: Typical indoor environment
        self.temperature = random.uniform(20.0, 30.0)   # 20-30°C
        self.humidity = random.uniform(30.0, 60.0)      # 30-60% RH
        
        # Initialize operational state
        self.status = "operational"
        self.total_swaps_today = random.randint(0, 50)  # Historical count
        self.last_swap_time = datetime.utcnow().isoformat() + "Z"
        
        logger.info(f"Initialized {station_id} with {self.battery_available} available batteries")
    
    def simulate_battery_charging(self):
        """
        Simulate batteries charging over time
        
        LOGIC:
        - 20% chance a charging battery finishes
        - Moves from charging to available
        - Realistic: batteries take time to charge
        """
        if self.battery_charging > 0 and random.random() < 0.2:  # 20% chance
            self.battery_charging -= 1
            self.battery_available += 1
            logger.debug(f"{self.station_id}: Battery finished charging")
    
    def simulate_battery_swap(self):
        """
        Simulate a customer performing a battery swap
        
        LOGIC:
        - 15% chance per update cycle
        - Takes available battery, puts depleted one in charging
        - Updates counters and timestamp
        
        WHY 15%: Creates realistic but noticeable activity
        """
        if self.battery_available > 0 and random.random() < 0.15:  # 15% chance
            self.battery_available -= 1
            self.battery_charging += 1
            self.total_swaps_today += 1
            self.last_swap_time = datetime.utcnow().isoformat() + "Z"
            logger.info(f"{self.station_id}: Battery swap performed (total today: {self.total_swaps_today})")
    
    def simulate_temperature_change(self):
        """
        Simulate gradual temperature changes
        
        LOGIC:
        - Small random walk (±0.5°C)
        - Bounded between 15-35°C
        - Mimics natural fluctuations
        
        WHY: Realistic sensor data shows gradual changes, not jumps
        """
        change = random.uniform(-0.5, 0.5)
        self.temperature = max(15.0, min(35.0, self.temperature + change))
    
    def simulate_humidity_change(self):
        """
        Simulate gradual humidity changes
        
        LOGIC:
        - Small random walk (±2%)
        - Bounded between 20-80%
        - Correlates loosely with temperature
        """
        change = random.uniform(-2.0, 2.0)
        self.humidity = max(20.0, min(80.0, self.humidity + change))
    
    def simulate_status_change(self):
        """
        Occasionally switch to maintenance mode
        
        LOGIC:
        - 1% chance to enter maintenance
        - 10% chance to exit maintenance
        
        WHY: Simulates real-world station downtime
        """
        if self.status == "operational" and random.random() < 0.01:  # 1% chance
            self.status = "maintenance"
            logger.warning(f"{self.station_id}: Entering maintenance mode")
        elif self.status == "maintenance" and random.random() < 0.10:  # 10% chance
            self.status = "operational"
            logger.info(f"{self.station_id}: Exiting maintenance mode")
    
    def update(self):
        """
        Run all simulation updates for one time step
        
        WHY: Centralizes all state changes in one method
        """
        self.simulate_battery_charging()
        self.simulate_battery_swap()
        self.simulate_temperature_change()
        self.simulate_humidity_change()
        self.simulate_status_change()
    
    def get_telemetry(self) -> StationState:
        """
        Get current state as telemetry message
        
        Returns:
            StationState object with current values
        """
        return StationState(
            station_id=self.station_id,
            battery_available=self.battery_available,
            battery_charging=self.battery_charging,
            temperature=round(self.temperature, 1),
            humidity=round(self.humidity, 1),
            status=self.status,
            total_swaps_today=self.total_swaps_today,
            last_swap_time=self.last_swap_time
        )


# ==============================================================================
# MQTT CONNECTION HANDLER
# ==============================================================================

class IoTSimulator:
    """
    Manages MQTT connection to AWS IoT Core and publishes telemetry
    
    WHY THIS CLASS:
    - Handles connection lifecycle (connect, disconnect)
    - Manages multiple stations
    - Publishes messages in a loop
    
    MQTT CONCEPTS:
    - Connection: Persistent TCP connection to IoT broker
    - Topic: Named channel for messages (like "ev/station/01/telemetry")
    - QoS 1: "At least once delivery" guarantee
    """
    
    def __init__(self, num_stations: int, interval: int):
        """
        Initialize IoT simulator
        
        Args:
            num_stations: Number of stations to simulate
            interval: Seconds between telemetry updates
        """
        self.num_stations = num_stations
        self.interval = interval
        self.stations: List[BatterySwapStation] = []
        self.mqtt_connection = None
        
        # Create simulated stations
        # WHY: Each station is independent with own state
        for i in range(1, num_stations + 1):
            station_id = f"station-{i:02d}"  # station-01, station-02, etc.
            self.stations.append(BatterySwapStation(station_id))
        
        logger.info(f"Created {num_stations} simulated stations")
    
    def connect_to_iot(self):
        """
        Establish MQTT connection to AWS IoT Core
        
        WHY: Must authenticate before publishing messages
        
        SECURITY:
        - Uses X.509 certificates for mutual TLS
        - Each device has unique certificate
        - AWS verifies certificate on connect
        """
        try:
            logger.info(f"Connecting to AWS IoT Core at {IOT_ENDPOINT}")
            
            # Build MQTT connection with AWS IoT SDK
            # WHY: Handles TLS, keepalive, reconnection logic
            self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=IOT_ENDPOINT,
                cert_filepath=IOT_CERT_PATH,
                pri_key_filepath=IOT_KEY_PATH,
                ca_filepath=IOT_CA_PATH,
                client_id=f"station-simulator-{int(time.time())}",  # Unique ID
                clean_session=False,  # Resume session if disconnect
                keep_alive_secs=30    # Send ping every 30s
            )
            
            # Connect synchronously
            # WHY: Block until connected or timeout
            connect_future = self.mqtt_connection.connect()
            connect_future.result()  # Wait for connection
            
            logger.info("Successfully connected to AWS IoT Core")
            
        except Exception as e:
            logger.error(f"Failed to connect to IoT Core: {str(e)}")
            raise
    
    def publish_telemetry(self, station: BatterySwapStation):
        """
        Publish telemetry message for one station
        
        Args:
            station: BatterySwapStation to publish data for
            
        MQTT TOPIC: ev/station/{station_id}/telemetry
        QoS LEVEL: 1 (at least once delivery)
        """
        try:
            # Get current telemetry
            telemetry = station.get_telemetry()
            
            # Add timestamp
            # WHY: Message generation time, not processing time
            telemetry_dict = telemetry.to_dict()
            telemetry_dict['timestamp'] = datetime.utcnow().isoformat() + "Z"
            
            # Convert to JSON
            payload = json.dumps(telemetry_dict)
            
            # Construct MQTT topic
            # WHY: Matches IoT Rule filter in Terraform
            topic = f"{TOPIC_PREFIX}/{station.station_id}/telemetry"
            
            # Publish message
            # QoS 1: Guarantees message delivered at least once
            # WHY: More reliable than QoS 0, but not duplicate-free like QoS 2
            publish_future = self.mqtt_connection.publish(
                topic=topic,
                payload=payload,
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            # Wait for publish to complete
            publish_future.result()
            
            logger.info(
                f"Published telemetry for {station.station_id}: "
                f"batteries={telemetry.battery_available}, temp={telemetry.temperature}°C"
            )
            
        except Exception as e:
            logger.error(f"Failed to publish for {station.station_id}: {str(e)}")
    
    def run(self):
        """
        Main simulation loop
        
        LOGIC:
        1. Update all station states
        2. Publish telemetry for each station
        3. Sleep for interval
        4. Repeat forever (until Ctrl+C)
        """
        try:
            # Connect to AWS IoT
            self.connect_to_iot()
            
            logger.info(f"Starting simulation loop (interval: {self.interval}s)")
            logger.info("Press Ctrl+C to stop")
            
            # Main loop
            while True:
                # Update and publish each station
                for station in self.stations:
                    station.update()
                    self.publish_telemetry(station)
                
                # Wait before next cycle
                logger.info(f"Sleeping for {self.interval} seconds...")
                time.sleep(self.interval)
        
        except KeyboardInterrupt:
            logger.info("Simulation stopped by user")
        
        except Exception as e:
            logger.error(f"Simulation error: {str(e)}", exc_info=True)
        
        finally:
            # Clean disconnect
            if self.mqtt_connection:
                logger.info("Disconnecting from AWS IoT Core")
                disconnect_future = self.mqtt_connection.disconnect()
                disconnect_future.result()


# ==============================================================================
# COMMAND LINE INTERFACE
# ==============================================================================

def main():
    """
    Parse command line arguments and start simulation
    
    USAGE:
        python station_simulator.py --num-stations 20 --interval 5
    """
    
    parser = argparse.ArgumentParser(
        description="Simulate EV battery swap stations sending telemetry to AWS IoT Core"
    )
    
    parser.add_argument(
        '--num-stations',
        type=int,
        default=10,
        help='Number of stations to simulate (default: 10)'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='Seconds between telemetry updates (default: 5)'
    )
    
    parser.add_argument(
        '--endpoint',
        type=str,
        help='AWS IoT Core endpoint (overrides default)'
    )
    
    args = parser.parse_args()
    
    # Override endpoint if provided
    global IOT_ENDPOINT
    if args.endpoint:
        IOT_ENDPOINT = args.endpoint
    
    # Validate configuration
    # WHY: Fail fast with clear error message
    if IOT_ENDPOINT.startswith("your-iot-endpoint"):
        logger.error("ERROR: Please configure IOT_ENDPOINT in the script or use --endpoint")
        logger.error("Find your endpoint: AWS Console > IoT Core > Settings")
        sys.exit(1)
    
    # Create and run simulator
    simulator = IoTSimulator(
        num_stations=args.num_stations,
        interval=args.interval
    )
    
    simulator.run()


if __name__ == "__main__":
    main()


# ==============================================================================
# EXAMPLE OUTPUT
# ==============================================================================
# When running, you'll see output like:
#
# 2024-01-15 14:30:00 - INFO - Created 10 simulated stations
# 2024-01-15 14:30:00 - INFO - Connecting to AWS IoT Core at xxx.iot.us-east-1.amazonaws.com
# 2024-01-15 14:30:01 - INFO - Successfully connected to AWS IoT Core
# 2024-01-15 14:30:01 - INFO - Starting simulation loop (interval: 5s)
# 2024-01-15 14:30:01 - INFO - Published telemetry for station-01: batteries=12, temp=25.3°C
# 2024-01-15 14:30:01 - INFO - Battery swap performed (total today: 88)
# 2024-01-15 14:30:01 - INFO - Published telemetry for station-02: batteries=10, temp=27.8°C
# ...