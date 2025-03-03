import axios from 'axios';

const BACKEND_URL = 'http://36.213.56.75:8002';

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

// 图生视频接口参数
export interface ImageToVideoParams {
  image_base64: string;    // Base64编码的图片数据
  prompt: string;          // 提示词
  steps?: number;          // 生成步数，默认10
  num_frames?: number;     // 帧数，默认81
}

// 视频生成任务状态
export interface VideoTaskStatus {
  task_id: number;
  status: 'pending' | 'queued' | 'initializing' | 'loading_model' | 'preparing_environment' | 'setting_parameters' |
         'loading_image' | 'preprocessing_image' | 'configuring_model' | 'preparing_prompt' | 'setting_sampler' |
         'configuring_scheduler' | 'preparing_inference' | 'inference' | 'postprocessing_frames' | 'preparing_video' |
         'combining_video' | 'optimizing_video' | 'postprocessing_video' | 'completed' | 'processing' | 'failed';
  progress: number;
  estimated_time: number | null;
  video_path: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  node_id?: string;
  node_status?: string;
  node_description?: string;
  queue_position?: number;
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

// 创建视频生成任务
export const createVideoGeneration = async (params: ImageToVideoParams) => {
  console.log('图生视频参数:', params);
  try {
    const response = await api.post('/api/i2v/create', params);
    return response.data;
  } catch (error) {
    console.error('图生视频请求错误:', error);
    throw error;
  }
}

// 获取视频生成任务状态
export const getVideoTaskStatus = async (taskId: number) => {
  try {
    const response = await api.get(`/api/i2v/status/${taskId}`);
    return response.data as VideoTaskStatus;
  } catch (error) {
    console.error(`获取任务 ${taskId} 状态错误:`, error);
    throw error;
  }
}

// 获取用户的所有视频生成任务
export const getUserVideoTasks = async () => {
  try {
    const response = await api.get(`/api/i2v/user`);
    return response.data.tasks;
  } catch (error) {
    console.error(`获取视频任务错误:`, error);
    throw error;
  }
} 