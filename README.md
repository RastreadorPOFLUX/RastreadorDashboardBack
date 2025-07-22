# Rastreador Solar Dashboard Backend

## 📋 Visão Geral

Backend FastAPI para o dashboard do rastreador solar POF-LUX, desenvolvido para integrar com frontend React. Este sistema fornece APIs REST e WebSocket para monitoramento e controle em tempo real do rastreador solar.

## 🚀 Características

- **FastAPI** - Framework moderno para APIs Python
- **WebSocket** - Comunicação em tempo real
- **CORS** - Configurado para integração com React
- **Documentação Automática** - Swagger UI integrado
- **Comunicação ESP** - Interface com ESP32/ESP8266
- **Agregação de Dados** - Processamento e cache inteligente
- **APIs Externas** - Proxy para dados climáticos

## 🏗️ Arquitetura

```
Backend/
├── app.py                      # Servidor principal FastAPI
├── models/
│   └── schemas.py             # Modelos Pydantic
├── services/
│   ├── esp_communicator.py    # Comunicação com ESP
│   ├── websocket_manager.py   # Gerenciador WebSocket
│   └── data_aggregator.py     # Agregação de dados
└── requirements.txt
```

## 📦 Instalação

### 1. Pré-requisitos

- Python 3.8+
- ESP32/ESP8266 conectado na rede local
- Frontend React rodando (porta 3000 ou 5173)
- Rustup instalado (link de instalação: https://rustup.rs/)
- Visual Studio 2017 ou superior instalado

### 2. Instalação das Dependências

```bash
cd RastreadorDashboardBack
```
Crie uma máquina virtual no seu projeto:

```bash
python -m venv venv
cd venv
Scripts/activate.ps1 (para termianal powershell);
Scripts/acrivate.bat (para terminal cmd).
```

Volte à pasta do projeto:

```bash
pip install -r requirements.txt
```

Atenção! Não commite sua máquina virtual no repositório do github, crie um arquivo .gitignore e adicione as pastas do ambiente virtual nesse arquivo.

### 3. Configuração

Edite o IP do ESP em `services/esp_communicator.py` se necessário:
```python
def __init__(self, esp_ip: str = "192.168.0.106", ...):
```

### 4. Execução

```bash
python app.py
```

O servidor estará disponível em:
- **API**: http://localhost:8000
- **Documentação**: http://localhost:8000/docs
- **WebSocket**: ws://localhost:8000/ws/live

## 📡 API Endpoints

### Saúde do Sistema

#### `GET /`
Endpoint de saúde básico
```json
{"message": "Rastreador Solar Dashboard API", "status": "online"}
```

#### `GET /api/health`
Verificação completa de saúde
```json
{
  "api_status": "online",
  "esp_status": true,
  "timestamp": 1640995200
}
```

### Dados em Tempo Real

#### `GET /api/angles`
Dados de ângulos para o componente AnglesCard
```json
{
  "sunPosition": 45.5,
  "lensAngle": 43.2,
  "manualSetpoint": 0.0
}
```

#### `GET /api/motor`
Dados do motor
```json
{
  "power": 50.2,
  "raw_value": 128
}
```

#### `GET /api/pid`
Dados do controlador PID
```json
{
  "kp": 2.0,
  "ki": 0.1,
  "kd": 0.05,
  "p": 4.6,
  "i": 0.23,
  "d": -0.15,
  "error": 2.3,
  "output": 128
}
```

#### `GET /api/system-status`
Status geral do sistema
```json
{
  "mode": "auto",
  "esp_clock": 1640995200,
  "rtc_day": 15,
  "rtc_month": 3,
  "rtc_year": 2024,
  "rtc_hour": 14,
  "rtc_minute": 30,
  "rtc_second": 45,
  "is_online": true
}
```

### Controle do Sistema

#### `PATCH /api/mode`
Alterar modo de operação
```json
// Request
{
  "mode": "auto"  // "auto", "manual", "halt", "presentation"
}

// Response
{
  "status": "success",
  "mode": "auto"
}
```

#### `PATCH /api/rtc`
Ajustar relógio do sistema
```json
// Request
{
  "timestamp": 1640995200
}

// Response
{
  "status": "success",
  "timestamp": 1640995200
}
```

### Dados de Rastreamento

#### `GET /api/tracking-data`
Download de dados históricos
```json
{
  "data": "timestamp,solar_angle,lens_angle,motor_power,error\n..."
}
```

#### `DELETE /api/tracking-data`
Limpar dados armazenados
```json
{
  "status": "success",
  "message": "Tracking data cleared"
}
```

### APIs Externas

#### `GET /api/weather/{city}?api_key={key}`
Proxy para dados climáticos
```json
{
  "temperature": 25.3,
  "humidity": 68.5,
  "pressure": 1013.2,
  "weather_description": "Partly cloudy",
  "cloudiness": 40.0
}
```

## 🔌 WebSocket API

### Conexão
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/live');
```

### Dados Recebidos
```json
{
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
    "is_online": true
  },
  "control_signals": {
    "motor_direction": "CW",
    "tracking_enabled": true,
    "manual_override": false,
    "safety_stop": false
  },
  "timestamp": 1640995200
}
```

## 🔧 Configuração Avançada

### Configuração CORS
Para permitir outros domínios:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://seu-dominio.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Configuração ESP
Para alterar IP do ESP:
```python
esp_communicator = ESPCommunicator(esp_ip="192.168.0.XXX")
```

### Configuração de Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)  # Para debug detalhado
```

## 🔄 Integração com Frontend React

### 1. Configurar Base URL
No React, configure a base URL da API:
```javascript
const API_BASE_URL = 'http://localhost:8000';
```

### 2. Requisições HTTP
```javascript
// Obter dados de ângulos
const anglesResponse = await fetch(`${API_BASE_URL}/api/angles`);
const anglesData = await anglesResponse.json();

// Alterar modo
await fetch(`${API_BASE_URL}/api/mode`, {
  method: 'PATCH',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({mode: 'auto'})
});
```

### 3. WebSocket
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/live');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Atualizar estado do React
  setSystemData(data);
};
```

## 🧪 Testes

### Teste de Conectividade
```bash
curl http://localhost:8000/api/health
```

### Teste de Modo
```bash
curl -X PATCH http://localhost:8000/api/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "auto"}'
```

### Teste WebSocket
```javascript
// No console do navegador
const ws = new WebSocket('ws://localhost:8000/ws/live');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

## 📊 Monitoramento

### Logs do Sistema
```bash
# Logs aparecem no terminal onde o servidor está rodando
INFO:     Started server process [1234]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Documentação Interativa
Acesse http://localhost:8000/docs para:
- Testar endpoints interativamente
- Ver documentação completa
- Visualizar schemas de dados

## 🔧 Troubleshooting

### Backend não inicia
1. Verificar dependências: `pip install -r requirements.txt`
2. Verificar porta: Alterar porta se 8000 estiver ocupada
3. Verificar Python: Usar Python 3.8+

### ESP não conecta
1. Verificar IP em `esp_communicator.py`
2. Testar conectividade: `ping 192.168.0.101`
3. Verificar se ESP está na mesma rede

### Frontend não conecta
1. Verificar CORS em `app.py`
2. Verificar porta do frontend em CORS
3. Testar endpoint: `curl http://localhost:8000/api/health`

### WebSocket falha
1. Verificar URL: `ws://localhost:8000/ws/live`
2. Verificar conexão ESP WebSocket
3. Ver logs no terminal do servidor

## 📈 Performance

- **Cache**: Dados são cacheados por 500ms
- **Rate Limiting**: Implementar se necessário
- **Async**: Todas operações são assíncronas
- **WebSocket**: Reconexão automática

## 🤝 Integração com Sistema Original

Este backend é compatível com:
- ESP32/ESP8266 do sistema POF-LUX original
- APIs HTTP do sistema original (`/config`, `/pof-lux/tracking`)
- Esquemas de dados do sistema original

## 📄 Licença

Desenvolvido como parte do projeto POF-LUX de iniciação científica.

---

*Para mais informações, consulte a documentação original do sistema POF-LUX.*


