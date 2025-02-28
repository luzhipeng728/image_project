import React, { useState, useEffect } from 'react';
import { Upload, Input, Button, Card, message, Spin, Radio, Select } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import api from '../utils/api';

const { Dragger } = Upload;
const { TextArea } = Input;
const { Option } = Select;

const StyledCard = styled(Card)`
  margin-bottom: 20px;
`;

const ImagePreview = styled.img`
  max-width: 100%;
  margin-top: 16px;
`;

interface Model {
  id: number;
  name: string;
  alias: string;
  current_price: number;
}

const ImageToImage: React.FC = () => {
  const [imageUrl, setImageUrl] = useState<string>('');
  const [previewUrl, setPreviewUrl] = useState<string>('');
  const [prompt, setPrompt] = useState<string>("参考以上图片，保留图片中的整体风格，生成一张优化后的图片，生成的图片描述必须是英文，图片中的存在文字，不需要描述，只需要描述图片中画面信息");
  const [loading, setLoading] = useState<boolean>(false);
  const [generatedImageUrl, setGeneratedImageUrl] = useState<string>('');
  const [uploadType, setUploadType] = useState<'file' | 'url'>('file');
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<number>(1);
  const [error, setError] = useState<string | null>(null);
  const [seed, setSeed] = useState<number>(0);

  // 获取模型列表
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await api.get('/api/generation/models');
        setModels(response.data);
        if (response.data.length > 0) {
          setSelectedModelId(response.data[0].id);
        }
      } catch (error) {
        console.error('获取模型列表失败:', error);
        message.error('获取模型列表失败');
      }
    };

    fetchModels();
  }, []);

  const handleUpload = async (file: File) => {
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await api.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        transformRequest: [(data) => data],
      });
      setImageUrl(response.data.url);
      setPreviewUrl(response.data.url);
      message.success('图片上传成功');
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail 
        ? (typeof error.response.data.detail === 'string' 
          ? error.response.data.detail 
          : JSON.stringify(error.response.data.detail))
        : '图片上传失败';
      message.error(errorMessage);
      console.error('Upload error:', error);
    }
    return false;
  };

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const url = e.target.value;
    setImageUrl(url);
    setPreviewUrl(url);
  };

  const handleGenerate = async () => {
    if (!imageUrl) {
      message.error('请先选择一张图片');
      return;
    }

    if (!selectedModelId) {
      message.error('请选择一个模型');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // 获取图片尺寸
      const img = new Image();
      img.src = previewUrl;
      
      // 等待图片加载完成
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error('图片加载失败'));
      });
      
      // 计算等比例缩放后的尺寸，确保宽高都小于1024
      let width = img.width;
      let height = img.height;
      console.log('------------------------------')
      console.log(width)
      console.log(height)
      console.log('------------------------------')
      const maxSize = 1024;
      
      if (width > maxSize || height > maxSize) {
        if (width > height) {
          // 宽度大于高度，以宽度为基准等比例缩放
          const ratio = maxSize / width;
          width = maxSize;
          height = Math.floor(height * ratio);
        } else {
          // 高度大于宽度，以高度为基准等比例缩放
          const ratio = maxSize / height;
          height = maxSize;
          width = Math.floor(width * ratio);
        }
        console.log(`图片已等比例缩放: ${img.width}x${img.height} -> ${width}x${height}`);
      }
      
      const token = localStorage.getItem('token');
      if (!token) {
        setError('未登录或登录已过期，请重新登录');
        message.error('未登录或登录已过期，请重新登录');
        setLoading(false);
        // 重定向到登录页
        window.location.href = '/login';
        return;
      }
      
      try {
        const response = await api.post('/api/generation/image-to-image', {
          image_url: imageUrl,
          prompt: prompt,
          model_id: selectedModelId,
          seed: seed,
          width: width,
          height: height
        });
        
        console.log('生成成功:', response.data);
        setGeneratedImageUrl(response.data.image_url);
        message.success('图片生成成功');
      } catch (error: any) {
        console.error('生成失败:', error);
        
        // 处理不同类型的错误
        if (error.response?.status === 422) {
          // 处理图片尺寸超限错误
          const errorData = error.response.data;
          if (errorData.detail && Array.isArray(errorData.detail)) {
            const sizeError = errorData.detail.find((d: any) => d.loc && d.loc.includes('size'));
            if (sizeError) {
              setError(`图片尺寸超过限制：${sizeError.msg}。请使用较小的图片（最大2048x2048像素）。`);
              message.error('图片尺寸超过限制，最大允许2048x2048像素', 5);
            } else {
              setError(`请求错误: ${JSON.stringify(errorData.detail)}`);
            }
          } else if (errorData.message) {
            setError(`图片尺寸超过限制：${errorData.message}。最大尺寸: ${errorData.max_size}x${errorData.max_size}，当前尺寸: ${errorData.current_size}`);
            message.error(`图片尺寸超过限制：${errorData.message}`, 5);
          } else {
            setError('图片尺寸超过限制，请使用较小的图片（最大2048x2048像素）');
          }
        } else if (error.response?.status === 400) {
          // 处理其他客户端错误
          setError(error.response.data.message || '请求参数错误');
          message.error(error.response.data.message || '请求参数错误', 5);
        } else {
          // 处理服务器错误
          setError(error.response?.data?.message || '服务器错误，请稍后重试');
          message.error(error.response?.data?.message || '服务器错误，请稍后重试', 5);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <StyledCard title="选择输入方式">
        <Radio.Group
          value={uploadType}
          onChange={(e) => {
            setUploadType(e.target.value);
            setPreviewUrl('');
            setImageUrl('');
          }}
        >
          <Radio.Button value="file">上传文件</Radio.Button>
          <Radio.Button value="url">输入URL</Radio.Button>
        </Radio.Group>
      </StyledCard>

      <StyledCard title="上传原始图片">
        {uploadType === 'file' ? (
          <Dragger
            accept="image/*"
            beforeUpload={handleUpload}
            showUploadList={false}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽图片到此区域上传</p>
          </Dragger>
        ) : (
          <Input
            placeholder="请输入图片URL"
            value={imageUrl}
            onChange={handleUrlChange}
          />
        )}
        {previewUrl && <ImagePreview src={previewUrl} alt="预览图" />}
      </StyledCard>

      <StyledCard title="选择模型">
        <Select
          style={{ width: '100%' }}
          value={selectedModelId}
          onChange={(value) => setSelectedModelId(value)}
        >
          {models.map(model => (
            <Option key={model.id} value={model.id}>
              {model.alias || model.name} {model.current_price > 0 ? `(${model.current_price}积分)` : ''}
            </Option>
          ))}
        </Select>
      </StyledCard>

      <StyledCard title="输入提示词">
        <TextArea
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="请输入描述性的提示词，用于生成新的图片..."
        />
        <Button
          type="primary"
          onClick={handleGenerate}
          loading={loading}
          style={{ marginTop: 16 }}
          block
        >
          生成图片
        </Button>
      </StyledCard>

      {loading && (
        <StyledCard>
          <div style={{ textAlign: 'center' }}>
            <Spin tip="正在生成图片..." />
          </div>
        </StyledCard>
      )}

      {generatedImageUrl && (
        <StyledCard title="生成结果">
          <ImagePreview src={generatedImageUrl} alt="生成的图片" />
        </StyledCard>
      )}

      {error && (
        <StyledCard title="错误信息">
          <p>{error}</p>
        </StyledCard>
      )}
    </>
  );
};

export default ImageToImage; 