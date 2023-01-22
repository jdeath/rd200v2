# rd200v2
RadonEye RD200 Version 2 Integration for Homeasssistant

Based on: https://github.com/EtoTen/radonreader/ and the AirThings BLE Homeassistant Integration (https://github.com/home-assistant/core/tree/dev/homeassistant/components/airthings_ble) and https://github.com/vincegio/airthings-ble

Only works for RD200 Version 2 units with serial numbers starting with either FR:RU (United States) , FR:RE (Spain) , FR:GI (???)

If you are pretty sure it is a version 2 device, but has a differnet serial number prefix, edit the manifest.json and line 152 in config_flow.py to include you prefix. If it works, post an issue or a PR and I can add it in.

Latest release might work for version 1 (FR:R2 serial numbers), but need testers to propose changes. V1 integration currently only supports current radon value, not long-term or peak readings.

A python script is posted for people to help find important fields.

If use ESPHome BT proxy, update to ESPHome 2022.12.4 to allow radon peak value to work correctly.

| Reading | Write Value | Data Location | Data Format | Unit | Added in Integration |
| - | - | - | - | - | - |
| `Current Radon` | `0x50` | `data[2:4]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Day Radon` | `0x50` | `data[4:6]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Month Radon` | `0x50` | `data[6:8]`??  | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Peak Radon` | `0x40` | `data[51:53]` | little endian ushort | Bq/m<sup>3<sup> | Yes |
| `Serial` | `0x40` | `data[8:11] + data[2:8] + data[11:15]` | chars |  | No |  
| `Model` | `0x40` | `data[16:21]` | chars |  | No |  
| `Firmware` | `0x40` | `data[22:30]` | chars |  | No |  
| `Uptime Minutes Field` | `0x51` | `data[4:6]` | little endian ushort | minutes  | Yes |  
| `Uptime Miliseconds Field` | `0x51` | `data[3:5]` | little endian ushort | miliseconds  | Yes | 
