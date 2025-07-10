import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from services.esp_communicator import ESPCommunicator

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataAggregator:
    """Classe para agregar e processar dados do ESP e outras fontes"""
    
    def __init__(self, esp_communicator: ESPCommunicator):
        self.esp_communicator = esp_communicator
        self.current_data = {}
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
            logger.warning("Data collection already running")
            return
        
        self.is_running = True
        logger.info("Starting data collection from ESP")
        
        # Iniciar listener WebSocket em uma tarefa separada
        async def websocket_callback(data):
            """Callback para processar dados recebidos via WebSocket"""
            await self.process_esp_data(data)
        
        # Criar tarefa para escutar WebSocket
        asyncio.create_task(
            self.esp_communicator.start_websocket_listener(websocket_callback)
        )
        
        # Loop principal de coleta de dados
        while self.is_running:
            try:
                # Verificar se dados via WebSocket estão atualizados
                last_esp_data = self.esp_communicator.get_last_data()
                
                if last_esp_data:
                    await self.process_esp_data(last_esp_data)
                else:
                    # Se não há dados do WebSocket, usar dados padrão
                    await self.process_esp_data(self.default_data)
                
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Error in data collection loop: {e}")
                await asyncio.sleep(2)  # Aguardar antes de tentar novamente
    
    def stop_data_collection(self) -> None:
        """Parar coleta de dados"""
        self.is_running = False
        logger.info("Data collection stopped")
    
    async def process_esp_data(self, raw_data: Dict[Any, Any]) -> None:
        """Processar dados brutos do ESP"""
        try:
            # Adicionar timestamp de processamento
            processed_data = raw_data.copy()
            processed_data["processed_timestamp"] = int(time.time())
            
            # Validar e normalizar dados
            processed_data = self.validate_and_normalize_data(processed_data)
            
            # Calcular dados derivados
            processed_data = self.calculate_derived_data(processed_data)
            
            # Atualizar dados atuais
            self.current_data = processed_data
            
            # Adicionar ao histórico
            self.add_to_history(processed_data)
            
            # Log ocasional para debug
            if int(time.time()) % 10 == 0:  # A cada 10 segundos
                logger.debug(f"Data processed: mode={processed_data.get('mode')}, "
                           f"sun_pos={processed_data.get('sun_position'):.1f}, "
                           f"lens_angle={processed_data.get('mpu', {}).get('lens_angle', 0):.1f}")
                           
        except Exception as e:
            logger.error(f"Error processing ESP data: {e}")
    
    def validate_and_normalize_data(self, data: Dict[Any, Any]) -> Dict[Any, Any]:
        """Validar e normalizar dados recebidos"""
        normalized = data.copy()
        
        # Garantir que campos essenciais existem
        normalized.setdefault("mode", "unknown")
        normalized.setdefault("esp_clock", int(time.time()))
        normalized.setdefault("motor", 0)
        normalized.setdefault("sun_position", 0.0)
        normalized.setdefault("manual_setpoint", 0.0)
        
        # Normalizar dados do MPU
        if "mpu" not in normalized:
            normalized["mpu"] = {"lens_angle": 0.0}
        elif "lens_angle" not in normalized["mpu"]:
            normalized["mpu"]["lens_angle"] = 0.0
        
        # Normalizar dados do PID
        if "pid_values" not in normalized:
            normalized["pid_values"] = {
                "kp": 0.0, "ki": 0.0, "kd": 0.0,
                "p": 0.0, "i": 0.0, "d": 0.0,
                "error": 0.0, "output": 0.0
            }
        
        # Normalizar dados de RTC
        now = datetime.now()
        normalized.setdefault("rtc_day", now.day)
        normalized.setdefault("rtc_month", now.month)
        normalized.setdefault("rtc_year", now.year)
        normalized.setdefault("rtc_hour", now.hour)
        normalized.setdefault("rtc_minute", now.minute)
        normalized.setdefault("rtc_second", now.second)
        
        # Validar ranges numéricos
        normalized["motor"] = max(0, min(255, normalized["motor"]))
        normalized["sun_position"] = max(-90, min(180, normalized["sun_position"]))
        normalized["manual_setpoint"] = max(-90, min(180, normalized["manual_setpoint"]))
        normalized["mpu"]["lens_angle"] = max(-90, min(180, normalized["mpu"]["lens_angle"]))
        
        return normalized
    
    def calculate_derived_data(self, data: Dict[Any, Any]) -> Dict[Any, Any]:
        """Calcular dados derivados"""
        processed = data.copy()
        
        # Calcular erro de rastreamento
        sun_pos = processed.get("sun_position", 0)
        lens_angle = processed.get("mpu", {}).get("lens_angle", 0)
        tracking_error = abs(sun_pos - lens_angle)
        processed["tracking_error"] = tracking_error
        
        # Calcular potência do motor em porcentagem
        motor_raw = processed.get("motor", 0)
        motor_percentage = (motor_raw / 255) * 100
        processed["motor_percentage"] = round(motor_percentage, 1)
        
        # Determinar direção do motor baseado no erro
        if tracking_error > 1:  # Limite de erro para movimento
            if sun_pos > lens_angle:
                motor_direction = "CW"  # Clockwise
            else:
                motor_direction = "CCW"  # Counter-clockwise
        else:
            motor_direction = "STOP"
        
        processed["motor_direction"] = motor_direction
        
        # Status de rastreamento
        mode = processed.get("mode", "unknown")
        tracking_enabled = mode in ["auto", "presentation"]
        processed["tracking_enabled"] = tracking_enabled
        
        # Override manual
        manual_override = mode == "manual"
        processed["manual_override"] = manual_override
        
        # Parada de segurança (baseado no modo halt ou erro muito alto)
        safety_stop = mode == "halt" or tracking_error > 45
        processed["safety_stop"] = safety_stop
        
        return processed
    
    def add_to_history(self, data: Dict[Any, Any]) -> None:
        """Adicionar dados ao histórico"""
        self.data_history.append(data.copy())
        
        # Manter tamanho máximo do histórico
        if len(self.data_history) > self.max_history_size:
            self.data_history.pop(0)
    
    async def get_current_data(self) -> Dict[Any, Any]:
        """Obter dados atuais (com cache)"""
        current_time = time.time()
        
        # Verificar cache
        if (current_time - self.last_update_time) < self.cache_duration and self.current_data:
            return self.current_data.copy()
        
        # Se não há dados atuais ou cache expirou, tentar obter do ESP
        if not self.current_data:
            esp_data = self.esp_communicator.get_last_data()
            if esp_data:
                await self.process_esp_data(esp_data)
            else:
                await self.process_esp_data(self.default_data)
        
        self.last_update_time = current_time
        return self.current_data.copy() if self.current_data else self.default_data.copy()
    
    def get_data_history(self, limit: int = 100) -> list:
        """Obter histórico de dados"""
        return self.data_history[-limit:] if limit > 0 else self.data_history.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obter estatísticas dos dados"""
        if not self.data_history:
            return {}
        
        recent_data = self.data_history[-100:]  # Últimos 100 pontos
        
        # Calcular estatísticas de erro de rastreamento
        tracking_errors = [d.get("tracking_error", 0) for d in recent_data]
        avg_error = sum(tracking_errors) / len(tracking_errors) if tracking_errors else 0
        max_error = max(tracking_errors) if tracking_errors else 0
        
        # Calcular estatísticas de potência do motor
        motor_powers = [d.get("motor_percentage", 0) for d in recent_data]
        avg_motor_power = sum(motor_powers) / len(motor_powers) if motor_powers else 0
        
        # Tempo de funcionamento em cada modo
        modes = [d.get("mode", "unknown") for d in recent_data]
        mode_counts = {}
        for mode in modes:
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        
        return {
            "average_tracking_error": round(avg_error, 2),
            "maximum_tracking_error": round(max_error, 2),
            "average_motor_power": round(avg_motor_power, 1),
            "mode_distribution": mode_counts,
            "data_points_collected": len(self.data_history),
            "collection_running": self.is_running
        }
    
    def get_current_timestamp(self) -> int:
        """Obter timestamp atual"""
        return int(time.time())
    
    async def force_data_refresh(self) -> Dict[Any, Any]:
        """Forçar atualização de dados (ignorar cache)"""
        self.last_update_time = 0
        return await self.get_current_data()
    
    def clear_history(self) -> None:
        """Limpar histórico de dados"""
        self.data_history.clear()
        logger.info("Data history cleared")
    
    def get_system_health(self) -> Dict[str, Any]:
        """Obter saúde do sistema de agregação"""
        esp_status = self.esp_communicator.get_connection_status()
        
        return {
            "aggregator_running": self.is_running,
            "last_update": self.last_update_time,
            "data_available": bool(self.current_data),
            "history_size": len(self.data_history),
            "esp_connection": esp_status,
            "cache_duration": self.cache_duration,
            "update_interval": self.update_interval
        } 