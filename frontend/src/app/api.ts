import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const startBot = async (config: any) => {
  const { data } = await api.post('/bot/start', config);
  return data;
};

export const stopBot = async () => {
  const { data } = await api.post('/bot/stop');
  return data;
};

export const getStrategies = async (): Promise<string[]> => {
  const { data } = await api.get('/strategies');
  return data;
};

export const getTrades = async () => {
  const { data } = await api.get('/bot/trades');
  return data;
};

export const getPerformance = async () => {
  const { data } = await api.get('/bot/performance');
  return data;
};

export const getMarkers = async () => {
  const { data } = await api.get('/bot/markers');
  return data;
};
