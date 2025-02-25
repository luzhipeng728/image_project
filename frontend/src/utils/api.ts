import axios from 'axios';

const BACKEND_URL = 'http://localhost:8002';

const api = axios.create({
  baseURL: BACKEND_URL,
});

// 请求拦截器添加token和处理Content-Type
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = token;
    }
    
    // 如果不是文件上传，设置默认的Content-Type
    if (!config.headers['Content-Type']) {
      config.headers['Content-Type'] = 'application/json';
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export interface GenerateImageParams {
  prompt: string;           // 提示词
  model_id: number;        // 模型ID - 这是必需的
  negative_prompt?: string; // 负面提示词
  width?: number;          // 图片宽度
  height?: number;         // 图片高度
  steps?: number;          // 推理步数
  seed?: number;           // 随机种子
  enhance?: boolean;       // 是否启用优化
}

export { BACKEND_URL };
export default api;

export const generateImage = async (params: GenerateImageParams) => {
  console.log('生图参数:', params);
  try {
    const response = await api.post('/api/generation/text-to-image', params);
    return response;
  } catch (error) {
    console.error('生图请求错误:', error);
    throw error;
  }
} 