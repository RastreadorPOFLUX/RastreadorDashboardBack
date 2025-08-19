import asyncio
import logging
import time
from typing import Dict, Any
from datetime import datetime
from services.esp_communicator import ESPCommunicator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class DataAggregator:
    """Classe para agregar e processar dados do ESP e outras fontes"""
    
    def __init__(self, esp_communicator: ESPCommunicator):
        self.esp_communicator = esp_communicator
        self.current_data: Dict[str, Any] = {}
        self.is_running = False
        self.update_interval = 1.0  # 1 segundo
        self.data_history = []
        self.max_history_size = 1000
        
        # Cache para evitar requisições excessivas
        self.last_update_time = 0
        self.cache_duration = 0.5  # 500ms de cache
        
        # Dados padrão para quando ESP não está disponível
        self.default_data = {
            "mode": "unknown",
            "esp_clock": int(time.time()),
            "rtc_day": datetime.now().day,
            "rtc_month": datetime.now().month,
            "rtc_year": datetime.now().year,
            "rtc_hour": datetime.now().hour,
            "rtc_minute": datetime.now().minute,
            "rtc_second": datetime.now().second,
            "motor": 0,
            "sun_position": 0.0,
            "manual_setpoint": 0.0,
            "mpu": {"lens_angle": 0.0},
            "pid_values": {
                "kp": 0.0,
                "ki": 0.0,
                "kd": 0.0,
                "p": 0.0,
                "i": 0.0,
                "d": 0.0,
                "error": 0.0,
                "output": 0.0
            }
        }

    async def start_data_collection(self) -> None:
        """Iniciar coleta contínua de dados do ESP"""
        if self.is_running:
            logger.warning("Data collection já está em execução")
            return

        self.is_running = True
        logger.info("Iniciando coleta de dados do ESP")

        # Callback para WebSocket
        async def websocket_callback(data: Dict[str, Any]):
            await self.process_esp_data(data)

        # Listener WebSocket em paralelo
        asyncio.create_task(
            self.esp_communicator.start_websocket_listener(websocket_callback)
        )

        # Loop de fallback — usa último dado conhecido ou default
        while self.is_running:
            try:
                last_esp_data = self.esp_communicator.get_last_data()
                if last_esp_data:
                    await self.process_esp_data(last_esp_data)
                else:
                    await self.process_esp_data(self.default_data)

                await asyncio.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Erro no loop de coleta: {e}")
            await asyncio.sleep(2)

    def stop_data_collection(self) -> None:
        self.is_running = False
        logger.info("Data collection stopped")

    async def process_esp_data(self, raw_data: Dict[str, Any]) -> None:
        """Processar dados brutos do ESP"""
        try:
            processed_data = raw_data.copy()
            processed_data["processed_timestamp"] = int(time.time())
            
            processed_data = self.validate_and_normalize_data(processed_data)
            processed_data = self.calculate_derived_data(processed_data)
            
            self.current_data = processed_data
            self.add_to_history(processed_data)
            
        except Exception as e:
            logger.error(f"Error processing ESP data: {e}")

    def validate_and_normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = data.copy()
        now = datetime.now()
        
        normalized.setdefault("mode", "unknown")
        normalized.setdefault("esp_clock", int(time.time()))
        normalized.setdefault("motor", 0)
        normalized.setdefault("sun_position", 0.0)
        normalized.setdefault("manual_setpoint", 0.0)
        normalized.setdefault("mpu", {"lens_angle": 0.0})
        normalized.setdefault("pid_values", {
            "kp": 0.0, "ki": 0.0, "kd": 0.0,
            "p": 0.0, "i": 0.0, "d": 0.0,
            "error": 0.0, "output": 0.0
        })
        normalized.setdefault("rtc_day", now.day)
        normalized.setdefault("rtc_month", now.month)
        normalized.setdefault("rtc_year", now.year)
        normalized.setdefault("rtc_hour", now.hour)
        normalized.setdefault("rtc_minute", now.minute)
        normalized.setdefault("rtc_second", now.second)
        
        # Limites numéricos
        normalized["motor"] = max(0, min(255, normalized["motor"]))
        normalized["sun_position"] = max(-90, min(90, normalized["sun_position"]))
        normalized["manual_setpoint"] = max(-90, min(90, normalized["manual_setpoint"]))
        normalized["mpu"]["lens_angle"] = max(-90, min(90, normalized["mpu"]["lens_angle"]))
        
        return normalized

    def calculate_derived_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        processed = data.copy()
        
        sun_pos = processed.get("sun_position", 0)
        lens_angle = processed.get("mpu", {}).get("lens_angle", 0)
        tracking_error = abs(sun_pos - lens_angle)
        processed["tracking_error"] = tracking_error
        
        motor_raw = processed.get("motor", 0)
        processed["motor_percentage"] = round((motor_raw / 255) * 100, 1)
        
        processed["motor_direction"] = (
            "CW" if tracking_error > 1 and sun_pos > lens_angle else
            "CCW" if tracking_error > 1 else "STOP"
        )
        
        mode = processed.get("mode", "unknown")
        processed["tracking_enabled"] = mode in ["auto", "presentation"]
        processed["manual_override"] = mode == "manual"
        processed["safety_stop"] = mode == "halt" or tracking_error > 45
        
        return processed

    def add_to_history(self, data: Dict[str, Any]) -> None:
        self.data_history.append(data)
        if len(self.data_history) > self.max_history_size:
            self.data_history.pop(0)

    async def get_current_data(self) -> Dict[str, Any]:
        current_time = time.time()
        if (current_time - self.last_update_time) < self.cache_duration and self.current_data:
            return self.current_data

        # Obter dados reais do ESP, ou usar padrão
        esp_data = self.esp_communicator.get_last_data()
        if not esp_data:
            esp_data = self.default_data

        await self.process_esp_data(esp_data)
        self.last_update_time = current_time
        return self.current_data

    def get_data_history(self, limit: int = 100) -> list:
        return self.data_history[-limit:] if limit > 0 else self.data_history

    def get_current_timestamp(self) -> int:
        return int(time.time())