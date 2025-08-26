from ultralytics import YOLO
import cv2
import serial
import time
import threading
from queue import Queue
import numpy as np

# --- Configuration ---
SERIAL_PORT = "COM5"
BAUD_RATE = 115200
MODEL_PATH = r"C:/models and data/iwd_model_20 1.pt"
WEBCAM_INDEX = 0  # Default webcam (0), change if you have multiple cameras

# Real-time processing parameters
TARGET_FPS = 30
FRAME_SKIP = 2  # Process every 2nd frame for better performance
CONFIDENCE_THRESHOLD = 0.5

class RealTimeDetector:
    def __init__(self):
        # Load YOLO model
        self.model = YOLO(MODEL_PATH)
        
        # Initialize webcam
        self.cap = cv2.VideoCapture(WEBCAM_INDEX)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
        
        # Check if webcam opened successfully
        if not self.cap.isOpened():
            raise RuntimeError("Error: Could not open webcam")
        
        # Initialize serial communication
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Allow ESP32 to reset
            print(f"Serial port {SERIAL_PORT} opened successfully")
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            self.ser = None
        
        # Threading variables
        self.frame_queue = Queue(maxsize=2)
        self.result_queue = Queue(maxsize=2)
        self.running = True
        self.frame_count = 0
        self.last_detection_time = time.time()
        self.current_status = "CHECKING"
        
        # FPS calculation
        self.fps_start_time = time.time()
        self.fps_frame_count = 0
        self.current_fps = 0
    
    def capture_frames(self):
        """Capture frames from webcam in a separate thread"""
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                # Skip frames for better performance
                if self.frame_count % FRAME_SKIP == 0:
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                self.frame_count += 1
            else:
                print("Error: Failed to capture frame")
                break
    
    def process_frames(self):
        """Process frames through YOLO model in a separate thread"""
        while self.running:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()
                
                # Run YOLO inference
                results = self.model(frame, conf=CONFIDENCE_THRESHOLD)[0]
                
                # Extract detection labels
                if results.boxes is not None:
                    labels = [self.model.names[int(cls)] for cls in results.boxes.cls]
                else:
                    labels = []
                
                # Check safety equipment
                has_helmet = any("helmet" in label.lower() for label in labels)
                has_vest = any("vest" in label.lower() for label in labels)
                
                # Determine status
                if has_helmet and has_vest:
                    status = "ACCESS_GRANTED"
                else:
                    status = "ACCESS_DENIED"
                
                # Add detection info to frame
                annotated_frame = results.plot()
                
                # Send to result queue
                if not self.result_queue.full():
                    self.result_queue.put((annotated_frame, status, labels))
    
    def send_to_esp32(self, status):
        """Send detection result to ESP32"""
        if self.ser and self.ser.is_open:
            try:
                message = status + "\n"
                self.ser.write(message.encode())
                self.ser.flush()
                print(f"Sent to ESP32: {status}")
            except serial.SerialException as e:
                print(f"Serial communication error: {e}")
    
    def calculate_fps(self):
        """Calculate current FPS"""
        self.fps_frame_count += 1
        if self.fps_frame_count >= 30:  # Calculate every 30 frames
            current_time = time.time()
            elapsed_time = current_time - self.fps_start_time
            self.current_fps = self.fps_frame_count / elapsed_time
            self.fps_start_time = current_time
            self.fps_frame_count = 0
    
    def run(self):
        """Main processing loop"""
        # Start threading
        capture_thread = threading.Thread(target=self.capture_frames)
        process_thread = threading.Thread(target=self.process_frames)
        
        capture_thread.daemon = True
        process_thread.daemon = True
        
        capture_thread.start()
        process_thread.start()
        
        print("Real-time detection started. Press 'q' to quit.")
        
        try:
            while self.running:
                if not self.result_queue.empty():
                    annotated_frame, status, labels = self.result_queue.get()
                    
                    # Send status to ESP32 if it changed
                    if status != self.current_status:
                        self.send_to_esp32(status)
                        self.current_status = status
                        self.last_detection_time = time.time()
                    
                    # Calculate FPS
                    self.calculate_fps()
                    
                    # Add status and FPS info to frame
                    cv2.putText(annotated_frame, f"Status: {status}", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(annotated_frame, f"FPS: {self.current_fps:.1f}", (10, 60), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(annotated_frame, f"Detected: {', '.join(labels)}", (10, 90), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    
                    # Display the frame
                    cv2.imshow('Real-Time Safety Detection', annotated_frame)
                
                # Check for quit key
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                # Send periodic status updates to ESP32
                if time.time() - self.last_detection_time > 5:  # Update every 5 seconds
                    self.send_to_esp32(self.current_status)
                    self.last_detection_time = time.time()
        
        except KeyboardInterrupt:
            print("Interrupted by user")
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up resources...")
        self.running = False
        
        if self.cap.isOpened():
            self.cap.release()
        
        if self.ser and self.ser.is_open:
            self.ser.close()
        
        cv2.destroyAllWindows()
        print("Cleanup complete")

# --- Main Execution ---
if __name__ == "__main__":
    try:
        detector = RealTimeDetector()
        detector.run()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cv2.destroyAllWindows()
