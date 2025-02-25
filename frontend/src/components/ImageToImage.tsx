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
      
      const response = await api.post('/upload', formData, {
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
      message.error('请先上传或输入图片URL');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post(`/api/generation/image-to-image`, {
        image_url: imageUrl,
        prompt: prompt || undefined,
        model_id: selectedModelId
      });

      setGeneratedImageUrl(response.data.image_url);
      message.success('图片生成成功');
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail 
        ? (typeof error.response.data.detail === 'string' 
          ? error.response.data.detail 
          : Array.isArray(error.response.data.detail)
            ? error.response.data.detail.map((err: any) => err.msg).join(', ')
            : JSON.stringify(error.response.data.detail))
        : '生成图片失败，请重试';
      message.error(errorMessage);
      console.error('Error:', error);
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
    </>
  );
};

export default ImageToImage; 