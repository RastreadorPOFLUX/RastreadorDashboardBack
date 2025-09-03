from pydantic import BaseModel, Field, IPvAnyAddress
from typing import Optional, Dict, Any
from enum import Enum


class OperationMode(str, Enum):
    """Modos de operação do sistema"""
    AUTO = "auto"
    MANUAL = "manual"
    HALT = "halt"
    PRESENTATION = "presentation"


# Schemas de Request (entrada)

class RTCAdjustRequest(BaseModel):
    """Request para ajustar RTC"""
    rtc: int = Field(..., description="Unix timestamp em segundos")
    
    class Config:
        schema_extra = {
            "example": {
                "rtc": 1640995200
            }
        }


class ModeRequest(BaseModel):
    """Request para alterar modo de operação"""
    mode: OperationMode
    manual_setpoint: int
    adjust: RTCAdjustRequest

    class Config:
        schema_extra = {
            "example": {
                "mode": "auto",
                "manual_setpoint": 0,
                "adjust":{
                    "rtc": 1640995200
                }
            }
        }


class DeviceRegistration(BaseModel):
    device_id: str
    ip: str


# Schemas de Response (saída)
class AnglesResponse(BaseModel):
    """Dados de ângulos para o componente AnglesCard"""
    sun_position: float = Field(..., description="Posição do sol em graus")
    lens_angle: float = Field(..., description="Ângulo atual da lente em graus")
    manual_setpoint: float = Field(..., description="Setpoint manual em graus")
    
    class Config:
        schema_extra = {
            "example": {
                "sun_position": 0,
                "lens_angle": 0,
                "manual_setpoint": 0
            }
        }

class ControlResponse(BaseModel):
    """Dados do controlador PID"""
    kp: float = Field(..., description="Constante proporcional")
    ki: float = Field(..., description="Constante integral")
    kd: float = Field(..., description="Constante derivativa")
    p: float = Field(..., description="Componente proporcional atual")
    i: float = Field(..., description="Componente integral atual")
    d: float = Field(..., description="Componente derivativa atual")
    error: float = Field(..., description="Erro atual")
    output: float = Field(..., description="Saída do controlador PID")
    
    class Config:
        schema_extra = {
            "example": {
                "kp": 2.0,
                "ki": 0.1,
                "kd": 0.05,
                "p": 4.6,
                "i": 0.23,
                "d": -0.15,
                "error": 2.3,
                "output": 128
            }
        }

class PIDAdjustResponse(BaseModel):
    """Request para ajustar PID"""
    kp: float = Field(..., description="Constante proporcional")
    ki: float = Field(..., description="Constante integral")
    kd: float = Field(..., description="Constante derivativa")
    
    class Config:
        schema_extra = {
            "example": {
                    "kp": 2.0,
                    "ki": 0.1,
                    "kd": 0.05
            }
        }


class PIDResponse(BaseModel):
    """Request para ajustar PID com valores atuais"""
    adjust: PIDAdjustResponse
    
    class Config:
        schema_extra = {
            "example": {
                "adjust": {
                    "kp": 2.0,
                    "ki": 0.1,
                    "kd": 0.05
                }
            }
        } 

class MotorResponse(BaseModel):
    """Dados do motor para os componentes de potência"""
    power: float = Field(..., description="Potência do motor em porcentagem (0-100)")
    raw_value: int = Field(..., description="Valor bruto PWM (0-255)")
    
    class Config:
        schema_extra = {
            "example": {
                "power": 50.2,
                "raw_value": 128
            }
        }



class SystemStatusResponse(BaseModel):
    """Status geral do sistema"""
    mode: str = Field(..., description="Modo de operação atual")
    esp_clock: int = Field(..., description="Clock do ESP em timestamp Unix")
    rtc_day: int = Field(..., description="Dia do RTC")
    rtc_month: int = Field(..., description="Mês do RTC")
    rtc_year: int = Field(..., description="Ano do RTC")
    rtc_hour: int = Field(..., description="Hora do RTC")
    rtc_minute: int = Field(..., description="Minuto do RTC")
    rtc_second: int = Field(..., description="Segundo do RTC")
    is_online: bool = Field(..., description="Status de conexão com ESP")
    
    class Config:
        schema_extra = {
            "example": {
                "mode": "auto",
                "esp_clock": 1640995200,
                "rtc_day": 15,
                "rtc_month": 3,
                "rtc_year": 2024,
                "rtc_hour": 14,
                "rtc_minute": 30,
                "rtc_second": 45,
                "is_online": True
            }
        }


# Schema completo para WebSocket
class WSMessage(BaseModel):
    """Mensagem completa do WebSocket"""
    angles: AnglesResponse
    motor: MotorResponse
    pid: PIDResponse
    system_status: SystemStatusResponse
    timestamp: int = Field(..., description="Timestamp da mensagem")
    
    class Config:
        schema_extra = {
            "example": {
                "angles": {
                    "sunPosition": 45.5,
                    "lensAngle": 43.2,
                    "manualSetpoint": 0.0
                },
                "motor": {
                    "power": 50.2,
                    "raw_value": 128
                },
                "pid": {
                    "kp": 2.0,
                    "ki": 0.1,
                    "kd": 0.05,
                    "p": 4.6,
                    "i": 0.23,
                    "d": -0.15,
                    "error": 2.3,
                    "output": 128
                },
                "system_status": {
                    "mode": "auto",
                    "esp_clock": 1640995200,
                    "rtc_day": 15,
                    "rtc_month": 3,
                    "rtc_year": 2024,
                    "rtc_hour": 14,
                    "rtc_minute": 30,
                    "rtc_second": 45,
                    "is_online": True
                },
                "timestamp": 1640995200
            }
        }


# Schemas para compatibilidade com o sistema original POF-LUX
class MPUData(BaseModel):
    """Dados do sensor MPU"""
    lens_angle: float


class PIDValues(BaseModel):
    """Valores do controlador PID (formato original)"""
    kp: float
    ki: float
    kd: float
    p: float
    i: float
    d: float
    error: float
    output: float


class ESPDataRaw(BaseModel):
    """Dados brutos recebidos do ESP (formato original)"""
    mode: str
    esp_clock: int
    rtc_day: int
    rtc_month: int
    rtc_year: int
    rtc_hour: int
    rtc_minute: int
    rtc_second: int
    motor: int
    sun_position: float
    manual_setpoint: float
    mpu: MPUData
    pid_values: PIDValues


# Schema de erro padrão
class ErrorResponse(BaseModel):
    """Resposta padrão para erros"""
    error: str = Field(..., description="Mensagem de erro")
    detail: Optional[str] = Field(None, description="Detalhes adicionais do erro")
    timestamp: int = Field(..., description="Timestamp do erro")
    
    class Config:
        schema_extra = {
            "example": {
                "error": "Connection failed",
                "detail": "Unable to connect to ESP32 device",
                "timestamp": 1640995200
            }
        } 