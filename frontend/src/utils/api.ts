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
      // 检查token是否已经包含Bearer前缀
      if (token.startsWith('Bearer ')) {
        config.headers.Authorization = token;
      } else {
        config.headers.Authorization = `Bearer ${token}`;
      }
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

// 响应拦截器处理401未授权错误
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response && error.response.status === 401) {
      // 清除本地存储的token
      localStorage.removeItem('token');
      
      // 显示错误提示
      alert(error.response.data.detail || '登录已过期，请重新登录');
      
      // 跳转到登录页面
      window.location.href = '/login';
    }
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