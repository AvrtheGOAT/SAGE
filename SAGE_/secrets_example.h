// Copy this file to secrets.h (same folder) and fill in real values.
// secrets.h is listed in .gitignore, so it never goes to GitHub.
#pragma once

const char* WIFI_SSID     = "your-wifi-or-hotspot-name";
const char* WIFI_PASSWORD = "your-wifi-password";

// Laptop running Flask: run `ipconfig` on the laptop to find its IP.
// Port must match the Flask app (default 5000).
const char* SERVER_URL    = "http://192.168.x.x:5000/readings";
