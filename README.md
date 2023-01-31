# rd200v2
RadonEye RD200 (Version 1 and 2) Integration for Homeasssistant

Based on: https://github.com/EtoTen/radonreader/ and the AirThings BLE Homeassistant Integration (https://github.com/home-assistant/core/tree/dev/homeassistant/components/airthings_ble) and https://github.com/vincegio/airthings-ble

Works for RD200 Version 2 units with serial numbers starting with either FR:RU (United States) , FR:RE (Spain) , FR:GI and FR:HA (??? both sold in the US). Now works for version 1 (FR:R2 serial numbers). V1 integration currently only supports current radon value, 1 day and 1 month readings. Note the box and the device display do not show the "FR:" portion of the serial number.

If you are pretty sure it is a version 2 device, but has a differnet serial number prefix, edit the manifest.json and line 152 in config_flow.py to include you prefix. If it works, post an issue or a PR and I can add it in.

A python script is posted for people to help find important fields in the V2.

If use ESPHome BT proxy, update to at least ESPHome 2022.12.4 to allow Version 2 radon peak value to work correctly.

### Installation Instructions
- Add this repo into HACS
- Install integration
- Restart Homeassistant
- Wait a few minutes and HA should find it automatically
- If not found automatically, Go to Settings->Device and Services->Add Integration (blue button at bottom right) -> search for RD200
- It should find it and set it up

Note: If used the ESPHome integration in the past, you must remove the RD200 MAC address from the `ble_client:` section. 

### Version 2 Data locations:
| Reading | Write Value | Data Location | Data Format | Unit | Added in Integration |
| - | - | - | - | - | - |
| `Current Radon` | `0x50` | `data[2:4]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Day Radon` | `0x50` | `data[4:6]` | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Average Month Radon` | `0x50` | `data[6:8]`  | little endian ushort | Bq/m<sup>3</sup> | Yes |
| `Peak Radon` | `0x40` | `data[51:53]` | little endian ushort | Bq/m<sup>3<sup> | Yes |
| `Serial` | `0x40` | `data[8:11] + data[2:8] + data[11:15]` | chars |  | No |  
| `Model` | `0x40` | `data[16:21]` | chars |  | No |  
| `Firmware` | `0x40` | `data[22:30]` | chars |  | No |  
| `Uptime Minutes Field` | `0x51` | `data[4:6]` | little endian ushort | minutes  | Yes |  
| `Uptime Miliseconds Field` | `0x51` | `data[3:5]` I think this is wrong, but who cares! | little endian ushort | miliseconds  | Yes | 
