"""Command operations for OnStar client."""
from typing import Any, Dict, List, Optional

from .types import (
    AlertRequestAction,
    AlertRequestOptions,
    AlertRequestOverride,
    ChargeOverrideMode,
    ChargeOverrideOptions,
    ChargingProfileChargeMode,
    ChargingProfileRateType,
    DiagnosticsRequestOptions,
    DoorRequestOptions,
    SetChargingProfileRequestOptions,
    TrunkRequestOptions,
)


class CommandFactory:
    """Factory for creating OnStar API command payloads."""
    
    @staticmethod
    def lock_door(options: Optional[DoorRequestOptions] = None) -> Dict[str, Any]:
        """Create lock door command payload.
        
        Parameters
        ----------
        options
            Optional parameters for the lock command
        """
        return {
            "lockDoorRequest": {
                "delay": 0,
                **(options or {})
            }
        }
    
    @staticmethod
    def unlock_door(options: Optional[DoorRequestOptions] = None) -> Dict[str, Any]:
        """Create unlock door command payload.
        
        Parameters
        ----------
        options
            Optional parameters for the unlock command
        """
        return {
            "unlockDoorRequest": {
                "delay": 0,
                **(options or {})
            }
        }
    
    @staticmethod
    def lock_trunk(options: Optional[TrunkRequestOptions] = None) -> Dict[str, Any]:
        """Create lock trunk command payload.
        
        Parameters
        ----------
        options
            Optional parameters for the lock trunk command
        """
        return {
            "lockTrunkRequest": {
                "delay": 0,
                **(options or {})
            }
        }
    
    @staticmethod
    def unlock_trunk(options: Optional[TrunkRequestOptions] = None) -> Dict[str, Any]:
        """Create unlock trunk command payload.
        
        Parameters
        ----------
        options
            Optional parameters for the unlock trunk command
        """
        return {
            "unlockTrunkRequest": {
                "delay": 0,
                **(options or {})
            }
        }
    
    @staticmethod
    def alert(options: Optional[AlertRequestOptions] = None) -> Dict[str, Any]:
        """Create alert command payload.
        
        Parameters
        ----------
        options
            Optional parameters for the alert command
        """
        return {
            "alertRequest": {
                "action": [AlertRequestAction.HONK.value, AlertRequestAction.FLASH.value],
                "delay": 0,
                "duration": 1,
                "override": [
                    AlertRequestOverride.DOOR_OPEN.value, 
                    AlertRequestOverride.IGNITION_ON.value
                ],
                **(options or {})
            }
        }
    
    @staticmethod
    def charge_override(options: Optional[ChargeOverrideOptions] = None) -> Dict[str, Any]:
        """Create charge override command payload.
        
        Parameters
        ----------
        options
            Optional parameters for the charge override command
        """
        options_dict = options or {}
        mode = options_dict.get("mode", ChargeOverrideMode.CHARGE_NOW)
        
        # Make sure we get the string value if an enum is passed
        mode_value = mode.value if hasattr(mode, "value") else mode
        
        return {
            "chargeOverrideRequest": {
                "mode": mode_value
            }
        }
    
    @staticmethod
    def set_charging_profile(options: Optional[SetChargingProfileRequestOptions] = None) -> Dict[str, Any]:
        """Create set charging profile command payload.
        
        Parameters
        ----------
        options
            Optional parameters for setting the charging profile
        """
        options_dict = options or {}
        
        charge_mode = options_dict.get("charge_mode", ChargingProfileChargeMode.IMMEDIATE)
        rate_type = options_dict.get("rate_type", ChargingProfileRateType.MIDPEAK)
        
        # Make sure we get the string values if enums are passed
        charge_mode_value = charge_mode.value if hasattr(charge_mode, "value") else charge_mode
        rate_type_value = rate_type.value if hasattr(rate_type, "value") else rate_type
        
        return {
            "chargingProfile": {
                "chargeMode": charge_mode_value,
                "rateType": rate_type_value
            }
        }
    
    @staticmethod
    def diagnostics(diagnostic_items: List[str]) -> Dict[str, Any]:
        """Create diagnostics command payload.
        
        Parameters
        ----------
        diagnostic_items
            List of diagnostic items to request
        """
        return {
            "diagnosticsRequest": {
                "diagnosticItem": diagnostic_items
            }
        }
    
    @staticmethod
    def set_hvac_settings(ac_mode: Optional[str] = None, heated_steering_wheel: Optional[bool] = None) -> Dict[str, Any]:
        """Create HVAC settings command payload.
        
        Parameters
        ----------
        ac_mode
            AC climate mode setting
        heated_steering_wheel
            Whether to enable heated steering wheel
        """
        hvac_settings = {}
        
        if ac_mode is not None:
            hvac_settings["acClimateSetting"] = ac_mode
            
        if heated_steering_wheel is not None:
            hvac_settings["heatedSteeringWheelEnabled"] = "true" if heated_steering_wheel else "false"
            
        return {"hvacSettings": hvac_settings}

    @staticmethod
    def cancel_alert() -> Dict[str, Any]:
        """Create cancel alert command payload."""
        return {
            "cancelAlertRequest": {}
        }
    
    @staticmethod
    def get_hotspot_info() -> Dict[str, Any]:
        """Create get hotspot info command payload."""
        return {
            "getHotspotInfoRequest": {}
        }
    
    @staticmethod
    def start(duration: int = 20) -> Dict[str, Any]:
        """Create remote start command payload.
        
        Parameters
        ----------
        duration
            Duration in minutes for the remote start
        """
        return {
            "startRequest": {
                "duration": duration
            }
        }
    
    @staticmethod
    def cancel_start() -> Dict[str, Any]:
        """Create cancel start command payload."""
        return {
            "cancelStartRequest": {}
        }
    
    @staticmethod
    def send_tbt_route(route_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create send turn-by-turn route command payload.
        
        Parameters
        ----------
        route_data
            Route data for the navigation
        """
        return {
            "sendTBTRouteRequest": route_data
        }
    
    @staticmethod
    def location() -> Dict[str, Any]:
        """Create location command payload."""
        return {
            "locationRequest": {}
        }
    
    @staticmethod
    def get_charging_profile() -> Dict[str, Any]:
        """Create get charging profile command payload."""
        return {
            "getChargingProfileRequest": {}
        }
    
    @staticmethod
    def get_commute_schedule() -> Dict[str, Any]:
        """Create get commute schedule command payload."""
        return {
            "getCommuteScheduleRequest": {}
        }
    
    @staticmethod
    def connect() -> Dict[str, Any]:
        """Create connect command payload."""
        return {
            "connectRequest": {}
        }
    
    @staticmethod
    def set_commute_schedule(schedule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create set commute schedule command payload.
        
        Parameters
        ----------
        schedule_data
            Commute schedule data
        """
        return {
            "setCommuteScheduleRequest": schedule_data
        }
    
    @staticmethod
    def stop_fast_charge() -> Dict[str, Any]:
        """Create stop fast charge command payload."""
        return {
            "stopFastChargeRequest": {}
        }
    
    @staticmethod
    def create_trip_plan(trip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create trip plan command payload.
        
        Parameters
        ----------
        trip_data
            Trip plan data
        """
        return {
            "createTripPlanRequest": trip_data
        }
    
    @staticmethod
    def get_trip_plan(trip_id: Optional[str] = None) -> Dict[str, Any]:
        """Create get trip plan command payload.
        
        Parameters
        ----------
        trip_id
            Optional trip ID to retrieve a specific trip plan
        """
        request = {}
        if trip_id:
            request["tripId"] = trip_id
            
        return {
            "getTripPlanRequest": request
        }
    
    @staticmethod
    def get_hotspot_status() -> Dict[str, Any]:
        """Create get hotspot status command payload."""
        return {
            "getHotspotStatusRequest": {}
        }
    
    @staticmethod
    def set_hotspot_info(ssid: str, passphrase: str) -> Dict[str, Any]:
        """Create set hotspot info command payload.
        
        Parameters
        ----------
        ssid
            WiFi SSID
        passphrase
            WiFi passphrase
        """
        return {
            "setHotspotInfoRequest": {
                "ssid": ssid,
                "passphrase": passphrase
            }
        }
    
    @staticmethod
    def disable_hotspot() -> Dict[str, Any]:
        """Create disable hotspot command payload."""
        return {
            "disableHotspotRequest": {}
        }
    
    @staticmethod
    def enable_hotspot() -> Dict[str, Any]:
        """Create enable hotspot command payload."""
        return {
            "enableHotspotRequest": {}
        }
    
    @staticmethod
    def stop_charge() -> Dict[str, Any]:
        """Create stop charge command payload."""
        return {
            "stopChargeRequest": {}
        }
    
    @staticmethod
    def get_charger_power_level() -> Dict[str, Any]:
        """Create get charger power level command payload."""
        return {
            "getChargerPowerLevelRequest": {}
        }
    
    @staticmethod
    def set_charger_power_level(level: int) -> Dict[str, Any]:
        """Create set charger power level command payload.
        
        Parameters
        ----------
        level
            Charger power level
        """
        return {
            "setChargerPowerLevelRequest": {
                "level": level
            }
        }
    
    @staticmethod
    def get_rate_schedule() -> Dict[str, Any]:
        """Create get rate schedule command payload."""
        return {
            "getRateScheduleRequest": {}
        }
    
    @staticmethod
    def set_rate_schedule(schedule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create set rate schedule command payload.
        
        Parameters
        ----------
        schedule_data
            Rate schedule data
        """
        return {
            "setRateScheduleRequest": schedule_data
        }
    
    @staticmethod
    def get_last_trip_electric_economy() -> Dict[str, Any]:
        """Create command payload to get last trip electric economy information."""
        return {
            "diagnosticsRequest": {
                "diagnosticItem": ["LAST TRIP ELECTRIC ECON"]
            }
        } 