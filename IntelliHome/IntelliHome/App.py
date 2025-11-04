import json
import time
import threading
import os
import logging
from datetime import datetime
from pathlib import Path

# Import your modules
from MQTT_communicator import MQTT_communicator
from environmental_module import environmental_module
from security_module import security_module
from device_control_module import device_control_module

# Configure logging
# Level changed from DEBUG to INFO to hide all debug text in the console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Adafruit IO Feed Keys ---
ENV_FEEDS = {
    "temperature": "temperature-feed",
    "humidity": "humidity-feed",
    "pressure": "pressure-feed"
}
SECURITY_FEEDS = {
    "motion_count": "motion-feed",
    "smoke_count": "smoke-feed",
    "sound_count": "sound-feed"
}
CONTROL_FEEDS = {
    "light": "light-control",
    "fan": "fan-control",
    "buzzer": "buzzer-control",
    "mode": "system-mode",
    # 🌟 NEW: Add Camera Control Feed
    "camera": "camera-trigger"
}
# ------------------------------

class DomiSafeApp:
    def __init__(self, config_file='config.json'):
        self.config = self.load_config(config_file)
        self.running = True
        self.system_mode = 'Home' # Initial Mode
        
        # Intervals from config
        self.security_check_interval = self.config.get('security_check_interval', 5)
        self.security_send_interval = self.config.get('security_send_interval', 360)
        self.env_interval = self.config.get('env_interval', 360)
        self.flushing_interval = self.config.get('flushing_interval', 10)

        # Initialize Modules
        self.mqtt_agent = MQTT_communicator(config_file)
        self.env_data = environmental_module(config_file)
        self.security_data = security_module(config_file)
        self.device_control = device_control_module(config_file) 
        
        self.setup_control_subscribers()

    def load_config(self, config_file):
        """Load configuration from JSON file"""
        default_config = {
             "security_check_interval": 5, "security_send_interval": 360,
             "env_interval": 360, "flushing_interval": 10,
             "cooldown_duration_sec": 10
        }
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            return default_config

    def setup_control_subscribers(self):
        """Set up command handler and subscribe to control feeds"""
        # 1. Set the handler for incoming messages
        self.mqtt_agent.set_command_handler(self.handle_incoming_mqtt_command)
        
        # 2. Subscribe to all necessary control feeds
        feeds_to_subscribe = list(CONTROL_FEEDS.values())
        self.mqtt_agent.subscribe_to_feeds(feeds_to_subscribe)
        logger.info(f"Subscribed to control feeds: {feeds_to_subscribe}")

    def handle_incoming_mqtt_command(self, feed_name, payload):
        
        # System Mode Selector Logic
        if feed_name == CONTROL_FEEDS['mode']:
            self.set_system_mode(payload)
            return

        # Manual Camera Trigger Logic 
        if feed_name == CONTROL_FEEDS['camera'] and payload.upper() in ('TAKE_PHOTO', '1'):
             logger.critical("📸 Remote Photo Triggered by Dashboard Command.")
             self.security_data.trigger_manual_capture() 
             
             self.mqtt_agent.send_to_adafruit_io(CONTROL_FEEDS['camera'], "PHOTO_TAKEN")
             return

        
        for device_name, feed_key in CONTROL_FEEDS.items():
            # Check if the feed is one of the actuators (not mode or camera)
            if feed_name == feed_key and device_name not in ('mode', 'camera'):
                # Process the command (turns on/off the physical pin and logs locally)
                self.device_control.process_command(device_name, payload)
                
                break
                
    def set_system_mode(self, new_mode_raw):
        
        new_mode = str(new_mode_raw).strip().title()
        
        # Only 'Home' and 'Away' are allowed modes now.
        if new_mode in ['Home', 'Away']: 
            self.system_mode = new_mode
            logger.critical(f"🚀 SYSTEM MODE UPDATED TO: {self.system_mode}")
            
        else:
            logger.warning(f"Invalid mode received: {new_mode_raw}. Mode remains {self.system_mode}")

    def send_to_cloud(self, data, feeds):
        """Send data to Adafruit IO by looping through sensor feeds"""
        success = True
        for sensor_name, feed_key in feeds.items():
            if sensor_name in data:
                # Use mqtt_agent to send sensor value to Adafruit_io
                if not self.mqtt_agent.send_to_adafruit_io(feed_key, data[sensor_name]):
                    success = False
                time.sleep(0.5) # Delay to avoid rate limiting
        return success
        
    def collect_environmental_data(self, current_time, timers, file_handle):
        """Collect and send environmental data every {env_interval} seconds"""
        if current_time - timers['env_check'] >= self.env_interval:
            env_data = self.env_data.get_environmental_data()
            file_handle.write(json.dumps(env_data) + "\n")
            if self.send_to_cloud(data=env_data, feeds=ENV_FEEDS):
                logger.info("Environmental data sent to cloud")
            else:
                logger.info("Offline, env data saved locally.")
            timers['env_check'] = current_time

    def collect_security_data(self, current_time, timers, security_counts, file_handle):
        """Check security and send summary every {security_send_interval} seconds"""
        
        # Check security every {security_check_interval} seconds
        if current_time - timers['security_check'] >= self.security_check_interval:
            sec_data = self.security_data.get_security_data()
            
            # Count detections for summary
            for key in ['motion', 'smoke', 'sound']:
                # Note: motion_detected is True ONLY if detection happened AND it passed the cooldown check
                if sec_data.get(f'{key}_detected', False): 
                    security_counts[key] += 1
            
            # Log to file if any detection occurred
            if any(sec_data.get(f'{key}_detected', False) for key in ['motion', 'smoke', 'sound']):
                file_handle.write(json.dumps(sec_data) + "\n")
            
            timers['security_check'] = current_time

        # Send summary to cloud every {security_send_interval} seconds
        if current_time - timers['security_send'] >= self.security_send_interval:
            security_summary = {
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'motion_count': security_counts['motion'],
                'smoke_count': security_counts['smoke'],
                'sound_count': security_counts['sound']
            }
            if self.send_to_cloud(data=security_summary, feeds=SECURITY_FEEDS):
                logger.info(f"Security summary sent: M:{security_counts['motion']}, S:{security_counts['smoke']}, A:{security_counts['sound']}")
            else:
                logger.warning("Failed to send security summary")
                
            # Reset counters
            security_counts['motion'] = 0
            security_counts['smoke'] = 0
            security_counts['sound'] = 0
            timers['security_send'] = current_time

    def data_collection_loop(self):
        """Main loop for all data collection and logging"""
        timestamp = datetime.now().strftime("%Y%m%d")
        
        # Define file paths
        environmental_data_filename = f"logs/{timestamp}_environmental_data.txt"
        security_data_filename = f"logs/{timestamp}_security_data.txt"
        device_status_filename = f"logs/{timestamp}_device_status.txt"
        
        Path("logs").mkdir(exist_ok=True) # Ensure a log directory exists
        
        # Open all files with line buffering (buffering=1) for frequent writing
        with open(environmental_data_filename, "a", buffering = 1) as file1, \
             open(security_data_filename, "a", buffering = 1) as file2, \
             open(device_status_filename, "a", buffering = 1) as file3:
            
            logger.info(f"Logging to files starting with {timestamp}_...")
            last_fsync = time.time()
            timers = {'env_check': 0, 'security_check': 0, 'security_send': 0}
            security_counts = {'motion': 0, 'smoke': 0, 'sound': 0}
            
            while self.running:
                try:
                    current_time = time.time()
                    
                    # 1. Environmental Data (Always runs)
                    self.collect_environmental_data(current_time, timers, file1)
                    
                    # 2. Security Data (System Mode Dependent)
                    # Security runs ONLY if mode is NOT 'Home' (i.e., 'Away')
                    if self.system_mode != 'Home': 
                        self.collect_security_data(current_time, timers, security_counts, file2)
                    # Note: The logger.debug message for security inactive is now suppressed by logging.INFO
                        
                    # 3. Device Status (Skipped for simplicity, as per note)
                    
                    # 4. Flush to Disk (Force write to disk)
                    if current_time - last_fsync > self.flushing_interval:
                        for fh in (file1, file2, file3):
                            fh.flush()
                            os.fsync(fh.fileno())
                        last_fsync = current_time
                        
                    # Sleep for the shortest interval
                    time.sleep(self.security_check_interval)
                    
                except Exception as e:
                    logger.error(f"Error in data collection loop: {e}", exc_info=True)
                    time.sleep(5) 
                    
    def start(self):
        """Start the DomiSafe application"""
        self.running = True
        logger.info("Starting DomiSafe IoT System")
        
        data_thread = threading.Thread(target=self.data_collection_loop)
        data_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("👋 Shutting down application...")
        finally:
            self.running = False
            # Wait for thread to exit so 'with' context closes and flushes files
            data_thread.join(timeout=10)
            
            # Clean up (Stop camera)
            try:
                # Check if picam2 is initialized and has a stop method before calling
                if hasattr(self.security_data, 'picam2') and callable(getattr(self.security_data.picam2, 'stop', None)):
                    self.security_data.picam2.stop() 
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                
            logger.info("Stopped.")


if __name__ == "__main__":
     #Using the already working DomiSafeApp config file from the already working previous lab.
      app = DomiSafeApp(config_file='./config.json') 
      app.start()
