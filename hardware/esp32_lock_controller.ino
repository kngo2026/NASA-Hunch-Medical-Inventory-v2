#include <WiFi.h>
#include <WebServer.h>

// ============================================================================
// CONFIGURATION - UPDATE THESE VALUES
// ============================================================================

const char* ssid = "Daniel's S25+";
const char* password = "sigmarizzlee10";

const int LOCK_PIN = 2;
const int DOOR_SENSOR_PIN = 5;

unsigned long UNLOCK_DURATION = 10000;  // 30 seconds

// ============================================================================
// GLOBAL VARIABLES
// ============================================================================

WebServer server(80);
bool isUnlocked = false;
unsigned long unlockTime = 0;
String lastUser = "";

// Door tracking
bool doorWasOpen = false;
unsigned long doorOpenTime = 0;
unsigned long lastDoorOpenDuration = 0;  
int doorOpenCount = 0;     

struct DoorEvent {
  unsigned long timestamp;
  unsigned long duration;
  String user;
};

const int MAX_DOOR_EVENTS = 20;
DoorEvent doorHistory[MAX_DOOR_EVENTS];
int doorEventCount = 0;

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LOCK_PIN, OUTPUT);
  pinMode(DOOR_SENSOR_PIN, INPUT_PULLUP);
  digitalWrite(LOCK_PIN, LOW);

  Serial.println("\n=================================");
  Serial.println("NASA Medical Cabinet Lock");
  Serial.println("Dual Mode: WiFi + Serial");
  Serial.println("=================================\n");

  connectToWiFi();

  server.on("/face-unlock", HTTP_POST, handleFaceUnlock);
  server.on("/unlock", HTTP_POST, handleFaceUnlock);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/door-history", HTTP_GET, handleDoorHistory);
  server.on("/", HTTP_GET, handleRoot);

  server.enableCORS(true);
  server.begin();

  Serial.println("Ready for commands!");
  Serial.print("WiFi IP: ");
  Serial.println(WiFi.localIP());
  Serial.println("Serial: USB");
  Serial.println("=================================\n");
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  server.handleClient();
  handleSerialCommands();
  monitorDoor();

  // Auto-relock after 30 seconds
  if (doorWasOpen) {
    lockCabinet();
  }
  if (isUnlocked && (millis() - unlockTime > UNLOCK_DURATION)) {
    lockCabinet();
  }
}

// ============================================================================
// DOOR MONITORING
// ============================================================================

void monitorDoor() {
  bool doorIsOpen = (digitalRead(DOOR_SENSOR_PIN) == LOW);
  if (doorIsOpen && !doorWasOpen) {
    doorOpenTime = millis();
    doorOpenCount++;
    doorWasOpen = true;

    Serial.println("--- Door Opened ---");
    Serial.print("Open count this session: ");
    Serial.println(doorOpenCount);
    Serial.print("Opened by: ");
    Serial.println(lastUser.length() > 0 ? lastUser : "Unknown");
    reportDoorEvent("opened", 0, lastUser);
  }

  if (!doorIsOpen && doorWasOpen) {
    unsigned long duration = millis() - doorOpenTime;
    lastDoorOpenDuration = duration;
    doorWasOpen = false;

    Serial.println("--- Door Closed ---");
    Serial.print("Was open for: ");
    printDuration(duration);

    if (doorEventCount < MAX_DOOR_EVENTS) {
      doorHistory[doorEventCount] = { millis(), duration, lastUser };
      doorEventCount++;
    } else {
      for (int i = 0; i < MAX_DOOR_EVENTS - 1; i++) {
        doorHistory[i] = doorHistory[i + 1];
      }
      doorHistory[MAX_DOOR_EVENTS - 1] = { millis(), duration, lastUser };
    }
    reportDoorEvent("closed", duration, lastUser);
  }
}

void printDuration(unsigned long ms) {
  unsigned long seconds = ms / 1000;
  unsigned long minutes = seconds / 60;
  seconds = seconds % 60;

  if (minutes > 0) {
    Serial.print(minutes);
    Serial.print("m ");
  }
  Serial.print(seconds);
  Serial.print("s (");
  Serial.print(ms);
  Serial.println("ms)");
}
void reportDoorEvent(String event, unsigned long duration, String user) {
  if (WiFi.status() != WL_CONNECTED) return;
  Serial.print("{\"door_event\":\"");
  Serial.print(event);
  Serial.print("\",\"duration_ms\":");
  Serial.print(duration);
  Serial.print(",\"user\":\"");
  Serial.print(user);
  Serial.println("\"}");
}

// ============================================================================
// DOOR HISTORY ENDPOINT
// ============================================================================

void handleDoorHistory() {
  String response = "{\"door_events\":[";

  for (int i = 0; i < doorEventCount; i++) {
    if (i > 0) response += ",";
    response += "{";
    response += "\"timestamp\":" + String(doorHistory[i].timestamp) + ",";
    response += "\"duration_ms\":" + String(doorHistory[i].duration) + ",";
    response += "\"duration_s\":" + String(doorHistory[i].duration / 1000) + ",";
    response += "\"user\":\"" + doorHistory[i].user + "\"";
    response += "}";
  }

  response += "],";
  response += "\"total_opens\":" + String(doorOpenCount) + ",";
  response += "\"door_currently_open\":" + String(doorWasOpen ? "true" : "false") + ",";
  response += "\"last_duration_ms\":" + String(lastDoorOpenDuration);
  response += "}";

  server.send(200, "application/json", response);
}

// ============================================================================
// SERIAL COMMAND HANDLER
// ============================================================================

void handleSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command.length() < 5) return;
    if (!command.startsWith("{")) return;

    Serial.println("Serial command: " + command);

    String action = "";
    String username = "Serial User";

    if (command.indexOf("\"action\"") > 0) {
      if (command.indexOf("\"unlock\"") > 0)       action = "unlock";
      else if (command.indexOf("\"lock\"") > 0)    action = "lock";
      else if (command.indexOf("\"status\"") > 0)  action = "status";
      else if (command.indexOf("\"door_history\"") > 0) action = "door_history";
    }

    int usernamePos = command.indexOf("\"username\"");
    if (usernamePos > 0) {
      int colonPos = command.indexOf(":", usernamePos);
      int quoteStart = command.indexOf("\"", colonPos);
      int quoteEnd = command.indexOf("\"", quoteStart + 1);
      if (quoteStart > 0 && quoteEnd > quoteStart) {
        username = command.substring(quoteStart + 1, quoteEnd);
      }
    }

    if (action == "unlock") {
      unlockCabinet(username);
      Serial.println("{\"success\":true,\"status\":\"unlocked\"}");
    } else if (action == "lock") {
      lockCabinet();
      Serial.println("{\"success\":true,\"status\":\"locked\"}");
    } else if (action == "status") {
      String status = isUnlocked ? "unlocked" : "locked";
      Serial.println("{\"success\":true,\"status\":\"" + status + "\",\"door_open\":" + String(doorWasOpen ? "true" : "false") + "}");
    } else if (action == "door_history") {
      Serial.print("{\"total_opens\":");
      Serial.print(doorOpenCount);
      Serial.print(",\"last_duration_ms\":");
      Serial.print(lastDoorOpenDuration);
      Serial.println("}");
    }
  }
}

// ============================================================================
// FACE UNLOCK HANDLER
// ============================================================================

void handleFaceUnlock() {
  Serial.println("\nWiFi unlock request received");

  String username = server.hasArg("username") ? server.arg("username") : "Unknown";
  String userId = server.hasArg("user_id") ? server.arg("user_id") : "0";

  Serial.print("Astronaut: ");
  Serial.println(username);

  unlockCabinet(username);

  String response = "{";
  response += "\"success\":true,";
  response += "\"status\":\"unlocked\",";
  response += "\"message\":\"Welcome " + username + "!\",";
  response += "\"unlock_duration\":30";
  response += "}";

  server.send(200, "application/json", response);
}

// ============================================================================
// STATUS HANDLER
// ============================================================================

void handleStatus() {
  String status = isUnlocked ? "unlocked" : "locked";
  int timeRemaining = 0;

  if (isUnlocked) {
    unsigned long elapsed = millis() - unlockTime;
    if (elapsed < UNLOCK_DURATION) {
      timeRemaining = (UNLOCK_DURATION - elapsed) / 1000;
    }
  }

  String response = "{";
  response += "\"lock\":\"" + status + "\",";
  response += "\"timeRemaining\":" + String(timeRemaining) + ",";
  response += "\"lastUser\":\"" + lastUser + "\",";
  response += "\"door\":\"" + String(doorWasOpen ? "open" : "closed") + "\",";
  response += "\"totalDoorOpens\":" + String(doorOpenCount) + ",";
  response += "\"lastDoorDurationMs\":" + String(lastDoorOpenDuration);
  response += "}";

  server.send(200, "application/json", response);
}

// ============================================================================
// HOME PAGE
// ============================================================================

void handleRoot() {
  String html = "<!DOCTYPE html><html><head>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<meta http-equiv='refresh' content='3'>";
  html += "<style>";
  html += "body{font-family:Arial;text-align:center;padding:20px;background:#0a0e27;color:white;}";
  html += "h1{color:#3b82f6;} .status{font-size:48px;margin:30px;}";
  html += ".locked{color:#ef4444;} .unlocked{color:#22c55e;}";
  html += ".door-open{color:#f97316;} .door-closed{color:#94a3b8;}";
  html += "table{margin:auto;border-collapse:collapse;font-size:14px;}";
  html += "td,th{padding:6px 12px;border:1px solid #334155;}";
  html += "</style></head><body>";
  html += "<h1>Medical Cabinet</h1>";
  html += "<div class='status " + String(isUnlocked ? "unlocked" : "locked") + "'>";
  html += isUnlocked ? "UNLOCKED" : "LOCKED";
  html += "</div>";

  if (isUnlocked) {
    unsigned long remaining = (UNLOCK_DURATION - (millis() - unlockTime)) / 1000;
    html += "<p>Auto-lock in: " + String(remaining) + " seconds</p>";
    html += "<p>Last unlocked by: " + lastUser + "</p>";
  }

  html += "<hr style='border-color:#334155;margin:20px auto;width:80%;'>";
  html += "<h2 class='" + String(doorWasOpen ? "door-open" : "door-closed") + "'>Door: " + String(doorWasOpen ? "OPEN" : "CLOSED") + "</h2>";
  html += "<p>Total opens this session: " + String(doorOpenCount) + "</p>";

  if (lastDoorOpenDuration > 0) {
    html += "<p>Last open duration: " + String(lastDoorOpenDuration / 1000) + " seconds</p>";
  }

  // Door history table
  if (doorEventCount > 0) {
    html += "<h3>Recent Door History</h3>";
    html += "<table><tr><th>#</th><th>User</th><th>Duration</th></tr>";
    int start = max(0, doorEventCount - 5);  // Show last 5
    for (int i = doorEventCount - 1; i >= start; i--) {
      html += "<tr><td>" + String(doorOpenCount - (doorEventCount - 1 - i)) + "</td>";
      html += "<td>" + doorHistory[i].user + "</td>";
      html += "<td>" + String(doorHistory[i].duration / 1000) + "s</td></tr>";
    }
    html += "</table>";
  }

  html += "<hr style='border-color:#334155;margin:20px auto;width:80%;'>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<p>Mode: WiFi + Serial</p>";
  html += "</body></html>";

  server.send(200, "text/html", html);
}

// ============================================================================
// LOCK CONTROL FUNCTIONS
// ============================================================================

void unlockCabinet(String user) {
  digitalWrite(LOCK_PIN, HIGH);
  isUnlocked = true;
  unlockTime = millis();
  lastUser = user;

  Serial.println("UNLOCKED");
  Serial.print("By: ");
  Serial.println(user);
  Serial.println("Auto-lock in 30 seconds\n");
}

void lockCabinet() {

  digitalWrite(LOCK_PIN, LOW);
  isUnlocked = false;

  Serial.println("LOCKED\n");
}

// ============================================================================
// WIFI CONNECTION
// ============================================================================

void connectToWiFi() {
  WiFi.disconnect(true);
  delay(1000);
  WiFi.mode(WIFI_STA);
  delay(100);

  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  Serial.print("Connecting");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 60) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm\n");
  } else {
    Serial.println("\nWiFi Failed!");
    Serial.println("Will use Serial mode only\n");
  }
}