import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getSessions = async () => {
  const { data } = await api.get('/sessions');
  return data;
};

export const startBot = async (config: any) => {
  const { data } = await api.post('/sessions/start', config);
  return data;
};

export const stopBot = async (sessionId: string) => {
  const { data } = await api.post(`/sessions/${sessionId}/stop`);
  return data;
};

export const runBacktest = async (config: any) => {
  const { data } = await api.post('/sessions/backtest', config);
  return data;
};

export const getStrategies = async (): Promise<string[]> => {
  const { data } = await api.get('/strategies');
  return data;
};

export const getTrades = async (sessionId: string) => {
  const { data } = await api.get(`/sessions/${sessionId}/trades`);
  return data;
};

export const getPerformance = async (sessionId: string) => {
  const { data } = await api.get(`/sessions/${sessionId}/performance`);
  return data;
};

export const getMarkers = async (sessionId: string) => {
  const { data } = await api.get(`/sessions/${sessionId}/markers`);
  return data;
};

export const deleteSession = async (sessionId: string) => {
  const { data } = await api.delete(`/sessions/${sessionId}`);
  return data;
};
