Olivier Dufort
Félix Méplon

Youtube short link: ...coming soon

Adafruit feeds link: https://io.adafruit.com/Olivieri/feeds

Adafruit dashboard link: https://io.adafruit.com/Olivieri/dashboards/intellihome

Project Reflexion:

The primary element that worked well was the MQTT Adafruit connection, which allowed for remote control and easy dashboard configuration. By separating the real-time communication handled with MQTT_communicator from the main application logic, the system has great responsiveness and does not overwhelm with data. This allowed for simultaneous sensor monitoring, data logging, and immediate processing of remote commands without the main loop freezing. The decision to manage logging locally before a daily upload also ensured data integrity in case of an internet outage, a crucial reliability feature.

The hardest challenge was undoubtedly managing the complexities of a overloading the system in Python, particularly around sensor cooldown and camera integration. Specifically, ensuring the camera only captured an image once per intrusion event, and not repeatedly due to cooldown issues, which required careful design within the security_module.py logic and had to be modified plenty of time.

If I could improve one thing, it would be the implementation of the daily cloud upload for the log files. Currently, the system logs data locally to the logs folder, but it lacks an automated script to push these files to long-term external cloud storage such as GoogleDrive. This would make the system more practical and life-like.

Main Adafruit pictures:

<img width="1457" height="685" alt="feeds" src="https://github.com/user-attachments/assets/f15852f3-0e63-4717-9907-c740f35dea16" />
<img width="619" height="427" alt="dashboard" src="https://github.com/user-attachments/assets/860420d7-9d9e-42ea-aa23-be29ea735930" />
<img width="1241" height="645" alt="temperature" src="https://github.com/user-attachments/assets/78714e76-7615-40e6-8d42-1aa87c6207b3" />
<img width="1237" height="607" alt="pressure" src="https://github.com/user-attachments/assets/f179b76f-de4f-45cd-bd00-5466f1045574" />
<img width="1266" height="579" alt="humidity" src="https://github.com/user-attachments/assets/4d2ce015-7c5c-4ca8-9902-2027fd0329a1" />
