# rd200v2
RadonEye RD200 Version 2 Integration for Homeasssistant

Based on: https://github.com/EtoTen/radonreader/ and the AirThings BLE Homeassistant Integration (https://github.com/home-assistant/core/tree/dev/homeassistant/components/airthings_ble) and https://github.com/vincegio/airthings-ble

Only works for RD200 Version 2 units with serial numbers starting with either FR:RU (United States) , FR:RE (Spain) , FR:GI (???)

If you are pretty sure it is a version 2 device, but has a differnet serial number prefix, edit the manifest.json and line 152 in config_flow.py to include you prefix. If it works, post an issue or a PR and I can add it in.

Latest releaae might work for version 1 (FR:R2 serial numbers), but probably will require a few testers to propose changes. V1 only supports current radon value, not long-term or peak readings.

A python script is posted for people to help find important fields.

Note for ESPHome BT Proxy: Retrieving the radon peak value is not stable. Usually works on first reboot of homeassistant, but many people have problems after that. USB Adapters do not have this problem. This is because the data is in a 68 byte long array and something (MTU??) is keeping ESPHome from returning more than 20 bytes after the first connection. An issue has been created: https://github.com/esphome/issues/issues/4041

| Reading | Write Value | Data Location | Data Format | Unit | Added in Integration |
| - | - | - | - | - | - |
| `Current Radon` | `0x50` | `data[2:4]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Day Radon` | `0x50` | `data[4:6]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Month Radon` | `0x50` | `data[6:8]`??  | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Peak Radon` | `0x40` | `data[51:53]` | little endian ushort | Bq/m<sup>3<sup> | Yes |
| `Serial` | `0x40` | `data[8:11] + data[2:8] + data[11:15]` | chars |  | No |  
| `Model` | `0x40` | `data[16:21]` | chars |  | No |  
| `Firmware` | `0x40` | `data[22:30]` | chars |  | No |  
| `Uptime` | ?? | ?? | ?? | ?? | No |  
