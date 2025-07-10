from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
import json
from typing import Dict, Any
import os

# Importações dos módulos locais
from models.schemas import *
from services.esp_communicator import ESPCommunicator
from services.websocket_manager import WSConnectionManager
from services.data_aggregator import DataAggregator

app = FastAPI(
    title="Rastreador Solar Dashboard API",
    description="API para comunicação com rastreador solar POF-LUX",
    version="1.0.0"
)

# Configurar CORS para permitir comunicação com o frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Vite e Create React App
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar serviços
esp_communicator = ESPCommunicator()
ws_manager = WSConnectionManager()
data_aggregator = DataAggregator(esp_communicator)

@app.on_event("startup")
async def startup_event():
    """Inicializar serviços ao iniciar a aplicação"""
    # Iniciar coleta de dados em background
    asyncio.create_task(data_aggregator.start_data_collection())

@app.get("/")
async def root():
    """Endpoint de saúde da API"""
    return {"message": "Rastreador Solar Dashboard API", "status": "online"}

@app.get("/api/health")
async def health_check():
    """Verificar saúde do sistema"""
    esp_status = await esp_communicator.check_connection()
    system_health = data_aggregator.get_system_health()
    
    return {
        "api_status": "online",
        "esp_status": esp_status,
        "timestamp": data_aggregator.get_current_timestamp(),
        "system_health": system_health
    }

# Endpoints de dados em tempo real
@app.get("/api/angles", response_model=AnglesResponse)
async def get_angles():
    """Obter dados de ângulos do sistema"""
    try:
        data = await data_aggregator.get_current_data()
        return AnglesResponse(
            sunPosition=data.get("sun_position", 0),
            lensAngle=data.get("mpu", {}).get("lens_angle", 0),
            manualSetpoint=data.get("manual_setpoint", 0)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/motor", response_model=MotorResponse)
async def get_motor_data():
    """Obter dados do motor"""
    try:
        data = await data_aggregator.get_current_data()
        motor_value = data.get("motor", 0)
        return MotorResponse(
            power=round((motor_value / 255) * 100, 1),  # Converter para porcentagem
            raw_value=motor_value
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pid", response_model=PIDResponse)
async def get_pid_data():
    """Obter dados do controlador PID"""
    try:
        data = await data_aggregator.get_current_data()
        pid_data = data.get("pid_values", {})
        return PIDResponse(
            kp=pid_data.get("kp", 0),
            ki=pid_data.get("ki", 0), 
            kd=pid_data.get("kd", 0),
            p=pid_data.get("p", 0),
            i=pid_data.get("i", 0),
            d=pid_data.get("d", 0),
            error=pid_data.get("error", 0),
            output=pid_data.get("output", 0)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system-status", response_model=SystemStatusResponse)
async def get_system_status():
    """Obter status geral do sistema"""
    try:
        data = await data_aggregator.get_current_data()
        return SystemStatusResponse(
            mode=data.get("mode", "unknown"),
            esp_clock=data.get("esp_clock", 0),
            rtc_day=data.get("rtc_day", 1),
            rtc_month=data.get("rtc_month", 1),
            rtc_year=data.get("rtc_year", 2024),
            rtc_hour=data.get("rtc_hour", 0),
            rtc_minute=data.get("rtc_minute", 0),
            rtc_second=data.get("rtc_second", 0),
            is_online=await esp_communicator.check_connection()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/control-signals", response_model=ControlSignalsResponse)
async def get_control_signals():
    """Obter sinais de controle do sistema"""
    try:
        data = await data_aggregator.get_current_data()
        return ControlSignalsResponse(
            motor_direction=data.get("motor_direction", "STOP"),
            tracking_enabled=data.get("tracking_enabled", False),
            manual_override=data.get("manual_override", False),
            safety_stop=data.get("safety_stop", False)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/solar-irradiation", response_model=SolarIrradiationResponse)
async def get_solar_irradiation():
    """Obter dados de irradiação solar (simulados por enquanto)"""
    try:
        data = await data_aggregator.get_current_data()
        # Por enquanto, vamos simular dados baseados no ângulo solar
        sun_position = data.get("sun_position", 0)
        
        # Simular irradiação baseada na posição do sol
        max_irradiation = 1200.0
        current_irradiation = max(0, max_irradiation * (sun_position / 90) * 0.8)
        
        return SolarIrradiationResponse(
            current_irradiation=round(current_irradiation, 1),
            peak_irradiation=max_irradiation,
            daily_average=round(max_irradiation * 0.65, 1)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/statistics")
async def get_statistics():
    """Obter estatísticas do sistema"""
    try:
        stats = data_aggregator.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoints de controle
@app.patch("/api/mode")
async def set_operation_mode(mode_request: ModeRequest):
    """Alterar modo de operação do sistema"""
    try:
        success = await esp_communicator.set_mode(mode_request.mode)
        if success:
            return {"status": "success", "mode": mode_request.mode}
        else:
            raise HTTPException(status_code=500, detail="Failed to set mode")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/rtc")
async def adjust_rtc(rtc_request: RTCAdjustRequest):
    """Ajustar relógio do sistema"""
    try:
        success = await esp_communicator.adjust_rtc(rtc_request.timestamp)
        if success:
            return {"status": "success", "timestamp": rtc_request.timestamp}
        else:
            raise HTTPException(status_code=500, detail="Failed to adjust RTC")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoints de dados
@app.get("/api/tracking-data")
async def download_tracking_data():
    """Download de dados de rastreamento"""
    try:
        csv_data = await esp_communicator.get_tracking_data()
        return JSONResponse(
            content={"data": csv_data},
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/tracking-data")
async def clear_tracking_data():
    """Limpar dados de rastreamento armazenados"""
    try:
        success = await esp_communicator.clear_tracking_data()
        if success:
            return {"status": "success", "message": "Tracking data cleared"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data-history")
async def get_data_history(limit: int = 100):
    """Obter histórico de dados"""
    try:
        history = data_aggregator.get_data_history(limit)
        return {"history": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket para dados em tempo real
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket para atualizações em tempo real"""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Aguardar dados do cliente (opcional)
            await asyncio.sleep(1)
            
            # Obter dados atuais
            current_data = await data_aggregator.get_current_data()
            
            # Estruturar dados para o WebSocket
            ws_data = {
                "angles": {
                    "sunPosition": current_data.get("sun_position", 0),
                    "lensAngle": current_data.get("mpu", {}).get("lens_angle", 0),
                    "manualSetpoint": current_data.get("manual_setpoint", 0)
                },
                "motor": {
                    "power": current_data.get("motor_percentage", 0),
                    "raw_value": current_data.get("motor", 0)
                },
                "pid": {
                    "kp": current_data.get("pid_values", {}).get("kp", 0),
                    "ki": current_data.get("pid_values", {}).get("ki", 0),
                    "kd": current_data.get("pid_values", {}).get("kd", 0),
                    "p": current_data.get("pid_values", {}).get("p", 0),
                    "i": current_data.get("pid_values", {}).get("i", 0),
                    "d": current_data.get("pid_values", {}).get("d", 0),
                    "error": current_data.get("pid_values", {}).get("error", 0),
                    "output": current_data.get("pid_values", {}).get("output", 0)
                },
                "system_status": {
                    "mode": current_data.get("mode", "unknown"),
                    "esp_clock": current_data.get("esp_clock", 0),
                    "rtc_day": current_data.get("rtc_day", 1),
                    "rtc_month": current_data.get("rtc_month", 1),
                    "rtc_year": current_data.get("rtc_year", 2024),
                    "rtc_hour": current_data.get("rtc_hour", 0),
                    "rtc_minute": current_data.get("rtc_minute", 0),
                    "rtc_second": current_data.get("rtc_second", 0),
                    "is_online": await esp_communicator.check_connection()
                },
                "control_signals": {
                    "motor_direction": current_data.get("motor_direction", "STOP"),
                    "tracking_enabled": current_data.get("tracking_enabled", False),
                    "manual_override": current_data.get("manual_override", False),
                    "safety_stop": current_data.get("safety_stop", False)
                },
                "timestamp": current_data.get("processed_timestamp", data_aggregator.get_current_timestamp())
            }
            
            # Enviar dados para o cliente
            await ws_manager.send_personal_json_message(ws_data, websocket)
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)

# Proxy para API de clima (evitar problemas de CORS)
@app.get("/api/weather/{city}", response_model=ClimateResponse)
async def get_weather_proxy(city: str, api_key: str):
    """Proxy para API de clima externa"""
    try:
        weather_data = await esp_communicator.get_weather_data(city, api_key)
        if weather_data:
            return ClimateResponse(**weather_data)
        else:
            # Retornar dados simulados se API externa falhar
            return ClimateResponse(
                temperature=25.0,
                humidity=60.0,
                pressure=1013.25,
                weather_description="Dados não disponíveis",
                cloudiness=50.0
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint para testar sem ESP (dados simulados)
@app.get("/api/demo-data")
async def get_demo_data():
    """Obter dados simulados para demonstração"""
    import time
    import math
    
    # Simular dados baseados no tempo
    current_time = time.time()
    angle_variation = math.sin(current_time / 10) * 30  # Varia entre -30 e 30
    
    demo_data = {
        "angles": {
            "sunPosition": 45 + angle_variation,
            "lensAngle": 43 + angle_variation * 0.9,  # Lente seguindo com pequeno erro
            "manualSetpoint": 0
        },
        "motor": {
            "power": abs(angle_variation) * 2,  # Potência baseada no erro
            "raw_value": int(abs(angle_variation) * 2 * 2.55)
        },
        "pid": {
            "kp": 2.0,
            "ki": 0.1,
            "kd": 0.05,
            "p": angle_variation * 2,
            "i": 0.5,
            "d": -0.2,
            "error": angle_variation * 0.1,
            "output": abs(angle_variation) * 2 * 2.55
        },
        "system_status": {
            "mode": "auto",
            "esp_clock": int(current_time),
            "rtc_day": 15,
            "rtc_month": 3,
            "rtc_year": 2024,
            "rtc_hour": 14,
            "rtc_minute": 30,
            "rtc_second": int(current_time) % 60,
            "is_online": True
        },
        "control_signals": {
            "motor_direction": "CW" if angle_variation > 0 else "CCW",
            "tracking_enabled": True,
            "manual_override": False,
            "safety_stop": False
        },
        "timestamp": int(current_time)
    }
    
    return demo_data

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)