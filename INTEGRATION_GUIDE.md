# Guia de Integração Frontend React ↔ Backend FastAPI

## 🎯 Objetivo

Este guia mostra como integrar o frontend React (`RastreadorDashboardFront`) com o backend FastAPI (`RastreadorDashboardBack`) para criar um dashboard funcional do rastreador solar.

## 📋 Pré-requisitos

- Backend FastAPI rodando em `http://localhost:8000`
- Frontend React pronto na pasta `RastreadorDashboardFront`
- ESP32/ESP8266 configurado (opcional para testes)

## 🔧 Configuração do Frontend

### 1. Instalar Dependências HTTP

No diretório do frontend React:

```bash
cd RastreadorDashboardFront
npm install axios  # Para requisições HTTP
```

### 2. Criar Serviços de API

Crie o arquivo `src/services/api.js`:

```javascript
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

// Instância configurada do axios
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Serviços de dados
export const apiServices = {
  // Dados em tempo real
  getAngles: () => api.get('/api/angles'),
  getMotor: () => api.get('/api/motor'),
  getPID: () => api.get('/api/pid'),
  getSystemStatus: () => api.get('/api/system-status'),
  getControlSignals: () => api.get('/api/control-signals'),
  getSolarIrradiation: () => api.get('/api/solar-irradiation'),
  
  // Controle
  setMode: (mode) => api.patch('/api/mode', { mode }),
  adjustRTC: (timestamp) => api.patch('/api/rtc', { timestamp }),
  
  // Dados históricos
  getTrackingData: () => api.get('/api/tracking-data'),
  clearTrackingData: () => api.delete('/api/tracking-data'),
  getDataHistory: (limit = 100) => api.get(`/api/data-history?limit=${limit}`),
  
  // Clima
  getWeather: (city, apiKey) => api.get(`/api/weather/${city}?api_key=${apiKey}`),
  
  // Dados de demonstração
  getDemoData: () => api.get('/api/demo-data'),
  
  // Saúde do sistema
  getHealth: () => api.get('/api/health'),
};

export default api;
```

### 3. Criar Hook WebSocket

Crie o arquivo `src/hooks/useWebSocket.js`:

```javascript
import { useState, useEffect, useRef } from 'react';

const WS_URL = 'ws://localhost:8000/ws/live';

export const useWebSocket = () => {
  const [data, setData] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const ws = useRef(null);
  const reconnectTimeout = useRef(null);

  const connect = () => {
    try {
      ws.current = new WebSocket(WS_URL);

      ws.current.onopen = () => {
        console.log('WebSocket Connected');
        setIsConnected(true);
        setError(null);
      };

      ws.current.onmessage = (event) => {
        try {
          const newData = JSON.parse(event.data);
          setData(newData);
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.current.onclose = () => {
        console.log('WebSocket Disconnected');
        setIsConnected(false);
        
        // Tentar reconectar após 3 segundos
        reconnectTimeout.current = setTimeout(() => {
          connect();
        }, 3000);
      };

      ws.current.onerror = (err) => {
        console.error('WebSocket Error:', err);
        setError('WebSocket connection failed');
      };

    } catch (err) {
      console.error('Error connecting to WebSocket:', err);
      setError('Failed to create WebSocket connection');
    }
  };

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  return { data, isConnected, error };
};
```

## 🔄 Atualizando Componentes Existentes

### 1. Atualizar AnglesCard/Data.tsx

```typescript
import { useState, useEffect } from 'react';
import { apiServices } from '../../services/api';

export default function getData() {
  const [data, setData] = useState({
    sunPosition: 0,
    lensAngle: 0,
    manualSetpoint: 0,
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await apiServices.getAngles();
        setData(response.data);
      } catch (error) {
        console.error('Error fetching angles data:', error);
        // Fallback para dados simulados
        const demoResponse = await apiServices.getDemoData();
        setData(demoResponse.data.angles);
      }
    };

    // Buscar dados iniciais
    fetchData();

    // Atualizar a cada 5 segundos
    const interval = setInterval(fetchData, 5000);

    return () => clearInterval(interval);
  }, []);

  return data;
}
```

### 2. Atualizar PIDParametersCard/Data.tsx

```typescript
import { useState, useEffect } from 'react';
import { apiServices } from '../../services/api';

export default function getData() {
  const [data, setData] = useState({
    Kp: 0,
    Ki: 0,
    Kd: 0,
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await apiServices.getPID();
        setData({
          Kp: response.data.kp,
          Ki: response.data.ki,
          Kd: response.data.kd,
        });
      } catch (error) {
        console.error('Error fetching PID data:', error);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 2000);

    return () => clearInterval(interval);
  }, []);

  return data;
}
```

### 3. Criar Hook para Modo de Operação

Crie `src/hooks/useOperationMode.js`:

```javascript
import { useState, useEffect } from 'react';
import { apiServices } from '../services/api';

export const useOperationMode = () => {
  const [mode, setMode] = useState('unknown');
  const [loading, setLoading] = useState(false);

  const changeMode = async (newMode) => {
    setLoading(true);
    try {
      await apiServices.setMode(newMode);
      setMode(newMode);
    } catch (error) {
      console.error('Error changing mode:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const fetchMode = async () => {
      try {
        const response = await apiServices.getSystemStatus();
        setMode(response.data.mode);
      } catch (error) {
        console.error('Error fetching mode:', error);
      }
    };

    fetchMode();
  }, []);

  return { mode, changeMode, loading };
};
```

## 📡 Integração Completa com WebSocket

### Componente Principal com WebSocket

Crie `src/components/RealTimeDataProvider.jsx`:

```jsx
import React, { createContext, useContext } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';

const RealTimeDataContext = createContext();

export const useRealTimeData = () => {
  const context = useContext(RealTimeDataContext);
  if (!context) {
    throw new Error('useRealTimeData must be used within RealTimeDataProvider');
  }
  return context;
};

export const RealTimeDataProvider = ({ children }) => {
  const { data, isConnected, error } = useWebSocket();

  return (
    <RealTimeDataContext.Provider value={{ data, isConnected, error }}>
      {children}
    </RealTimeDataContext.Provider>
  );
};
```

### Atualizar App.tsx

```tsx
import "./App.css";
import { Routes, Route } from "react-router";
import { RealTimeDataProvider } from './components/RealTimeDataProvider';

// Páginas
import GeneralInfo from "./pages/GeneralInfo/index";
import ElectricalInfo from "./pages/ElectricalInfo/index";
import ControlInfo from "./pages/ControlInfo/index";
import CameraDisplay from "./pages/CameraDisplay/index";

// Estilo
import { GlobalStyle } from "./global";

export default function App() {
  return (
    <div className="App">
      <GlobalStyle />
      <RealTimeDataProvider>
        <Routes>
          <Route index path="*" element={<GeneralInfo />} />
          <Route path="/electricalInfo" element={<ElectricalInfo />} />
          <Route path="/controlInfo" element={<ControlInfo />} />
          <Route path="/cameraDisplay" element={<CameraDisplay />} />
        </Routes>
      </RealTimeDataProvider>
    </div>
  );
}
```

## 🎮 Componentes de Controle

### Exemplo: Botões de Modo de Operação

```jsx
import React from 'react';
import { useOperationMode } from '../../hooks/useOperationMode';

const OperationModeCard = () => {
  const { mode, changeMode, loading } = useOperationMode();

  const modes = [
    { key: 'auto', label: 'AUTO', color: 'green' },
    { key: 'manual', label: 'MANUAL', color: 'blue' },
    { key: 'halt', label: 'HALT', color: 'red' },
    { key: 'presentation', label: 'APRESENTAÇÃO', color: 'purple' }
  ];

  return (
    <div className="operation-mode-card">
      <h3>Modo de Operação</h3>
      <div className="mode-buttons">
        {modes.map(({ key, label, color }) => (
          <button
            key={key}
            className={`mode-button ${mode === key ? 'active' : ''}`}
            onClick={() => changeMode(key)}
            disabled={loading}
            style={{
              backgroundColor: mode === key ? color : 'gray',
              opacity: loading ? 0.6 : 1
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <p>Modo atual: <strong>{mode}</strong></p>
    </div>
  );
};

export default OperationModeCard;
```

## 📊 Monitoramento de Status

### Componente de Status de Conexão

```jsx
import React from 'react';
import { useRealTimeData } from '../RealTimeDataProvider';

const ConnectionStatus = () => {
  const { isConnected, error } = useRealTimeData();

  return (
    <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
      <div className="status-indicator">
        <span className={`dot ${isConnected ? 'green' : 'red'}`}></span>
        <span>{isConnected ? 'Conectado' : 'Desconectado'}</span>
      </div>
      {error && <div className="error-message">{error}</div>}
    </div>
  );
};

export default ConnectionStatus;
```

## 🚀 Iniciando o Sistema Completo

### 1. Terminal 1 - Backend

```bash
cd RastreadorDashboardBack
python app.py
```

### 2. Terminal 2 - Frontend

```bash
cd RastreadorDashboardFront
npm start
# ou
npm run dev
```

### 3. Verificar Integração

1. **Backend**: http://localhost:8000/docs
2. **Frontend**: http://localhost:3000 (ou 5173)
3. **Teste API**: http://localhost:8000/api/demo-data

## 🔍 Debugging

### Logs do Backend

```bash
# Backend mostra logs em tempo real
INFO:     Started server process [1234]
INFO:     New WebSocket connection. Total connections: 1
```

### Console do Frontend

```javascript
// No DevTools do navegador
// Verificar requisições
fetch('http://localhost:8000/api/health')
  .then(res => res.json())
  .then(console.log);

// Testar WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/live');
ws.onmessage = (e) => console.log('WS Data:', JSON.parse(e.data));
```

## ✅ Checklist de Integração

- [ ] Backend rodando na porta 8000
- [ ] Frontend rodando na porta 3000/5173
- [ ] CORS configurado corretamente
- [ ] Serviços de API implementados
- [ ] WebSocket conectando
- [ ] Componentes recebendo dados
- [ ] Controles funcionando
- [ ] Fallbacks para dados simulados

## 📝 Próximos Passos

1. **Conectar ESP real** - Configurar IP do ESP
2. **Melhorar UI** - Indicadores visuais de status
3. **Error Handling** - Tratamento robusto de erros
4. **Caching** - Implementar cache no frontend
5. **Otimização** - Reduzir frequência de requests

---

*Este guia cobre a integração básica. Para funcionalidades avançadas, consulte a documentação completa dos componentes.* 