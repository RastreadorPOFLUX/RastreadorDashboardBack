from datetime import datetime
from ipaddress import ip_address
from typing import Union
from fastapi import FastAPI, Request, Response, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
import time
import logging
import json
import urllib.parse

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importações dos módulos locais
from models.schemas import *
from services.esp_communicator import ESPCommunicator
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
esp_communicator = None
data_aggregator = None


def check_registered(communicator: Union[ESPCommunicator, DataAggregator]):
    """Verificar se o ESP está registrado e logar o status"""
    if communicator is None:
        raise HTTPException(status_code=503, detail="ESP não registrado.")


@app.get("/")
async def root():
    """Endpoint de saúde da API"""
    return {"message": "Rastreador Solar Dashboard API", "status": "online"}

@app.post("/registerIP")
async def register_esp_device(request: Request):
    """Registrar/atualizar IP do ESP. Aceita JSON ou form-urlencoded."""
    global esp_communicator, data_aggregator

    # Lê o body bruto e tenta parsear como JSON ou form-urlencoded
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8", errors="replace").strip()
    content_type = request.headers.get("content-type", "").lower()

    device_ip = None
    device_id = None

    try:
        if "application/json" in content_type or body_str.startswith("{"):
            body_data = json.loads(body_str)
            device_ip = body_data.get("ip")
            device_id = body_data.get("device_id", "esp32")
        else:
            # Tenta form-urlencoded
            parsed = dict(urllib.parse.parse_qsl(body_str))
            device_ip = parsed.get("ip")
            device_id = parsed.get("device_id", "esp32")
    except Exception as e:
        logger.error(f"Erro ao parsear body do /registerIP: {e} | body: {body_str!r}")
        raise HTTPException(status_code=400, detail=f"Body inválido: {str(e)}")

    if not device_ip:
        raise HTTPException(status_code=400, detail="Campo 'ip' é obrigatório.")

    try:
        parsed_ip = str(ip_address(device_ip.strip()))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"IP inválido: {device_ip}")

    logger.info(f"Requisição recebida de {request.client.host}")
    logger.info(f"Dados recebidos: device_id={device_id}, ip={parsed_ip}")

    if esp_communicator is None:
        # Primeira vez: cria o comunicador e inicia o agregador de dados
        esp_communicator = ESPCommunicator(esp_ip=parsed_ip, device_id=device_id)
        data_aggregator = DataAggregator(esp_communicator)
        asyncio.create_task(data_aggregator.start_data_collection())
        logger.info("ESPCommunicator criado e DataAggregator iniciado.")
    else:
        # Apenas atualiza IP/porta sem exigir que o ESP esteja online
        esp_communicator.update_esp_config(new_ip=parsed_ip)
        if device_id:
            esp_communicator.device_id = device_id
        logger.info(f"ESPCommunicator atualizado para IP {parsed_ip}")

    return {
        "status": "Sucesso",
        "message": f"ESP registrado/atualizado com IP {parsed_ip}",
        "connection_info": {"base_url": esp_communicator.base_url}
    }

@app.get("/api/health")
async def health_check():
    """Verificar saúde geral do sistema"""
    try:
        if esp_communicator is None:
            return {
                "api_status": "online",
                "esp_status": False,
                "esp_registered": False,
                "data_aggregator_status": False,
                "timestamp": int(time.time()),
                "system_health": {
                    "status": "Não iniciado",
                    "message": "ESP não registrado"
                }
            }
        esp_status = await esp_communicator.check_connection()
        current_timestamp = int(time.time())
        return {
            "api_status": "online",
            "esp_status": esp_status,
            "esp_registered": True,
            "data_aggregator_status": data_aggregator is not None,
            "timestamp": current_timestamp,
            "system_health": {
                "status": "ok" if esp_status else "error",
                "message": "OK" if esp_status else "Erro de conexão"
            },
            "connection_details": {
                "base_url": esp_communicator.base_url,
                "connected": esp_communicator.connection_status.get("connected", False),
                "last_error": esp_communicator.connection_status.get("last_error")
            }
        }
    except Exception as e:
        logger.error(f"Erro ao verificar saúde do sistema: {str(e)}")
        return {
            "api_status": "error",
            "esp_status": False,
            "esp_registered": esp_communicator is not None,
            "data_aggregator_status": data_aggregator is not None,
            "timestamp": int(time.time()),
            "system_health": {
                "status": "error",
                "message": f"Erro interno: {str(e)}"
            }
        }

# Endpoints de dados em tempo real
@app.get("/api/angles", response_model=AnglesResponse)
async def get_angles():
    """Obter dados de ângulos reais do ESP32"""
    check_registered(esp_communicator)
    try:
        # Obter dados atuais do agregador que inclui dados do WebSocket
        esp_data =  await esp_communicator.get_angles_from_esp()
        
        # Extrair e validar os dados necessários
        sun_position = esp_data.get("sunAngle", 0.0)
        lens_angle = esp_data.get("lensAngle", 0.0)  
        if lens_angle == 0.0: 
            lens_angle = esp_data.get("mpu", {}).get("lensAngle", 0.0)
        manual_setpoint = esp_data.get("manualSetpoint", 0.0)
        
        # Garantir que todos os valores são float
        angles_data = AnglesResponse(
            sun_position=float(sun_position),
            lens_angle=float(lens_angle),
            manual_setpoint=float(manual_setpoint)
        )
        
        return angles_data
    except Exception as e:
        logger.error(f"Erro ao obter dados de ângulos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/sensorsData", response_model=SensorsDataResponse)
async def get_sensors_data():
    """Obter dados dos sensores (piranômetro, fotodetector, temperatura, inundação)"""
    check_registered(esp_communicator)
    try:
        esp_data =  await esp_communicator.get_sensors_data_from_esp()
        pyranometer_data = esp_data.get("pyranometer", 0.0)
        photodetector_data = esp_data.get("photodetector", 0.0)
        temperature_data = esp_data.get("temperature", 0.0)
        flooding_data = esp_data.get("flooding", 0.0)

        # Garantir que todos os valores são float
        sensors_data = SensorsDataResponse(
            pyranometer_power=float(pyranometer_data),
            photodetector_power=float(photodetector_data),
            temperature_power=float(temperature_data),
            flooding_power=float(flooding_data)
        )
        
        return sensors_data
    except Exception as e:
        logger.error(f"Erro ao obter dados dos sensores: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pid", response_model=ControlResponse)
async def get_pid_data():
    check_registered(esp_communicator)
    try:
        esp_data =  await esp_communicator.get_pid_from_esp()
        # Extrair e validar os dados necessários
        kp = esp_data.get("kp", 0.0)
        ki = esp_data.get("ki", 0.0)  
        kd = esp_data.get("kd", 0.0)
        p = esp_data.get("p", 0.0)
        i = esp_data.get("i", 0.0)
        d = esp_data.get("d", 0.0)
        error = esp_data.get("error", 0.0)
        output = esp_data.get("output", 0.0)
        # Garantir que todos os valores são float
        pidParameters_data = ControlResponse(
            kp=float(kp),
            ki=float(ki),
            kd=float(kd),
            p=float(p),
            i=float(i),
            d=float(d),
            error=float(error),
            output=float(output)
        )
        return pidParameters_data
    except Exception as e:
        logger.error(f"Erro ao obter dados de parâmtros PID: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/motor", response_model=MotorResponse)
async def get_motor_data():
    """Obter dados do motor"""
    check_registered(esp_communicator)
    try:
        data = await esp_communicator.get_motor_power_from_esp()
        motor_value = data.get("pwm", 0)

        # Garantir que todos os valores são float
        motor_data = MotorResponse(
            power=round((motor_value / 255) * 100, 1),  # Converter para porcentagem
            raw_value=int(motor_value)  # Valor bruto PWM
        )

        return motor_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/api/system-status", response_model=SystemStatusResponse)
async def get_system_status():
    """Obter status geral do sistema"""
    check_registered(data_aggregator)
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


# Endpoints de controle
@app.patch("/api/mode")
async def set_operation_mode(mode_request: ModeRequest):
    """Alterar modo de operação do sistema"""
    check_registered(esp_communicator)
    try:
        success = await esp_communicator.set_mode(mode_request.mode, mode_request.manual_setpoint)
        if success:
            return {"status": "success", 
                    "mode": mode_request.mode,
                    "manual_setpoint": mode_request.manual_setpoint,
                    "adjusted_rtc": int(datetime.now().timestamp())}
        else:
            raise HTTPException(status_code=500, detail="Failed to set mode")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.patch("/api/adjustPid")
async def adjust_pid(pid_request: PIDResponse):
    """Ajustar parâmetros PID do ESP"""
    check_registered(esp_communicator)
    
    try:
        # Validar e ajustar os valores PID
        kp = pid_request.adjust.kp
        ki = pid_request.adjust.ki
        kd = pid_request.adjust.kd
        
        if not (0 <= kp <= 10 and 0 <= ki <= 10 and 0 <= kd <= 10):
            raise HTTPException(status_code=400, detail="Valores PID fora dos limites permitidos.")
        
        success = await esp_communicator.set_pid_parameters(kp, ki, kd)
        
        if success:
            return {"status": "success", "message": "Parâmetros PID ajustados com sucesso."}
        else:
            raise HTTPException(status_code=500, detail="Falha ao ajustar parâmetros PID no ESP.")
    except Exception as e:
        logger.error(f"Erro ao ajustar PID: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
    

# Endpoints de dados
@app.get("/api/tracking-data")
async def download_tracking_data():
    """Download de dados de rastreamento (CSV)"""
    check_registered(esp_communicator)
    
    try:
        # Verificar se o arquivo existe diretamente tentando acessá-lo
        csv_data = await esp_communicator.get_tracking_data()
        
        if not csv_data or len(csv_data.strip()) == 0:
            raise HTTPException(status_code=404, detail="Arquivo de tracking está vazio ou não contém dados")
        
        
        # Retorna como texto CSV
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=tracking.csv",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter dados de tracking: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    

@app.delete("/api/tracking-data")
async def clear_tracking_data():
    """Limpar dados de rastreamento armazenados"""
    check_registered(esp_communicator)
    try:
        success = await esp_communicator.clear_tracking_data()
        if success:
            return {"status": "success", "message": "Tracking data cleared"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear data")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# WebSocket para dados em tempo real
@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    # Aceita qualquer origem para evitar erro 403 em ambiente de desenvolvimento
    await websocket.accept()
    try:
        while True:
            # Monte o payload com os dados atuais
            angles = None
            pid = None
            system_status = None
            motor = None
            control_signals = None
            timestamp = int(time.time())
            try:
                if esp_communicator:
                    angles = await esp_communicator.get_angles_from_esp()
                    pid = await esp_communicator.get_pid_from_esp()
                    motor = await esp_communicator.get_motor_power_from_esp()
                if data_aggregator:
                    system_status = await data_aggregator.get_current_data()
            except Exception as e:
                logger.error(f"Erro ao coletar dados para WebSocket: {e}")
            payload = {
                "angles": angles,
                "pid": pid,
                "system_status": system_status,
                "motor": motor,
                "timestamp": timestamp
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1) # Envia a cada 0.5 segundo (500ms)
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado")
    except Exception as e:
        logger.error(f"Erro no WebSocket: {e}")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)