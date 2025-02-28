import React, { useState, useEffect } from 'react';
import { 
  Upload, Button, message, Select, Card, Radio, 
  Space, Progress, List, Image, Typography, Spin 
} from 'antd';
import { 
  UploadOutlined, FolderOpenOutlined, 
  FileZipOutlined, InboxOutlined 
} from '@ant-design/icons';
import type { UploadFile, UploadProps, RcFile } from 'antd/es/upload/interface';
import api from '../utils/api';
import axios from 'axios';

const { Option } = Select;
const { Dragger } = Upload;
const { Title, Text } = Typography;

interface Project {
  id: number;
  name: string;
  description: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

interface UploadedImage {
  id: number;
  file_path: string;
  file_type: string;
  width?: number;
  height?: number;
  project_id: number;
}

interface ImageUploadProps {
  selectedProject?: string;
  onProjectChange?: (projectId: string) => void;
  onUploadComplete?: (images: UploadedImage[]) => void;
}

const ImageUpload: React.FC<ImageUploadProps> = ({ selectedProject, onProjectChange, onUploadComplete }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [uploadType, setUploadType] = useState<string>('single');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [loadingProjects, setLoadingProjects] = useState<boolean>(false);
  const uploadRef = React.useRef<any>(null);
  const [folderUploadComplete, setFolderUploadComplete] = useState<boolean>(false);

  // 获取项目列表
  useEffect(() => {
    const fetchProjects = async () => {
      setLoadingProjects(true);
      try {
        const response = await api.get('/api/projects/');
        setProjects(response.data);
        if (response.data.length > 0) {
          setSelectedProjectId(response.data[0].id);
        }
      } catch (error) {
        console.error('获取项目列表失败:', error);
        message.error('获取项目列表失败');
      } finally {
        setLoadingProjects(false);
      }
    };

    fetchProjects();
  }, []);

  // 处理项目选择变化
  const handleProjectChange = (value: number) => {
    setSelectedProjectId(value);
  };

  // 处理上传类型变化
  const handleUploadTypeChange = (e: any) => {
    setUploadType(e.target.value);
    setFileList([]);
    setUploading(false);
    setUploadProgress(0);
    setFolderUploadComplete(false);
  };

  // 处理文件列表变化
  const handleFileChange = (info: any) => {
    // 过滤掉已上传成功的文件
    const filteredFileList = info.fileList.filter((file: any) => file.status !== 'done');
    setFileList(filteredFileList);
  };

  // 处理上传按钮点击
  const handleUploadClick = () => {
    // 检查是否有文件要上传
    if (!fileList || fileList.length === 0) {
      message.warning('请先选择要上传的文件');
      return;
    }
    
    // 检查是否选择了项目
    if (!selectedProjectId) {
      message.error('请先选择一个项目');
      return;
    }
    
    // 检查是否已经在上传中
    if (uploading) {
      message.warning('上传已在进行中，请等待当前上传完成');
      return;
    }
    
    // 触发上传
    if (uploadRef.current) {
      uploadRef.current.upload.submit();
    }
  };

  // 自定义上传操作
  const handleCustomRequest = async ({ file, onProgress, onSuccess, onError }: any) => {
    // 如果已经在上传中，防止重复提交
    if (uploading) {
      console.log('上传已在进行中，请等待当前上传完成');
      message.warning('上传已在进行中，请等待当前上传完成');
      return;
    }

    // 检查是否选择了项目
    if (!selectedProjectId) {
      message.error('请先选择一个项目');
      onError(new Error('请先选择一个项目'));
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    
    try {
      const formData = new FormData();
      
      if (uploadType === 'single') {
        // 单张图片上传
        formData.append('files', file);
      } else if (uploadType === 'folder') {
        // 文件夹上传 - 需要处理多个文件
        // 当使用directory属性时，会触发多次customRequest，每个文件一次
        // 所以这里只需要添加当前文件
        formData.append('files', file);
      } else if (uploadType === 'zip') {
        // ZIP文件上传
        formData.append('files', file);
      }
      
      formData.append('upload_type', uploadType);
      
      const response = await api.post(
        `/api/projects/${selectedProjectId}/upload`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          onUploadProgress: (progressEvent) => {
            const percent = Math.round((progressEvent.loaded * 100) / (progressEvent.total || 1));
            onProgress({ percent });
            setUploadProgress(percent);
          },
        }
      );

      console.log(response.data);
      
      // 上传成功处理
      if (response.data && response.data.results?.length > 0) {
        // 合并新上传的图片与已有的上传图片
        setUploadedImages(prev => [...prev, ...response.data.results]);
        message.success(`成功上传 ${response.data.results.length} 张图片`);
        
        // 刷新项目图片列表
        if (onUploadComplete) {
          onUploadComplete(response.data.results);
        }
      }
      
      onSuccess(response);
    } catch (error: any) {
      console.error('上传失败:', error);
      const errorMessage = error.response?.data?.detail || '上传失败，请重试';
      message.error(errorMessage);
      onError(error);
    } finally {
      // 只有在单张图片或ZIP上传完成后才重置状态
      // 文件夹上传会触发多次请求，所以不能在每次请求后都重置
      if (uploadType !== 'folder' || fileList.length <= 1) {
        setUploading(false);
        setUploadProgress(0);
        setFileList([]);
      }
    }
  };

  // 处理文件夹上传完成
  const handleFolderUploadComplete = () => {
    setUploading(false);
    setUploadProgress(0);
    setFileList([]);
    setFolderUploadComplete(false);
    message.success('文件夹上传已完成');
  };

  // 渲染上传组件
  const renderUploadComponent = () => {
    const uploadProps = {
      name: 'files',
      multiple: uploadType !== 'single',
      fileList,
      customRequest: handleCustomRequest,
      onChange: handleFileChange,
      accept: uploadType === 'zip' ? '.zip' : 'image/*',
      showUploadList: true,
      directory: uploadType === 'folder',
      beforeUpload: (file: RcFile) => {
        // 检查文件类型
        if (uploadType === 'zip') {
          const isZip = file.type === 'application/zip' || file.type === 'application/x-zip-compressed' || file.name.endsWith('.zip');
          if (!isZip) {
            message.error('只能上传ZIP文件!');
            return Upload.LIST_IGNORE;
          }
        } else {
          const isImage = file.type.startsWith('image/');
          if (!isImage) {
            message.error('只能上传图片文件!');
            return Upload.LIST_IGNORE;
          }
        }
        return true;
      },
    };

    // 根据上传类型选择不同的图标
    const uploadIcon = () => {
      if (uploadType === 'single') return <InboxOutlined />;
      if (uploadType === 'folder') return <FolderOpenOutlined />;
      return <FileZipOutlined />;
    };

    return (
      <div className="upload-container">
        <Upload.Dragger {...uploadProps} ref={uploadRef}>
          <p className="ant-upload-drag-icon">
            {uploadIcon()}
          </p>
          <p className="ant-upload-text">
            {uploadType === 'single' ? '点击或拖拽图片到此区域上传' :
             uploadType === 'folder' ? '点击或拖拽文件夹到此区域上传' :
             '点击或拖拽ZIP文件到此区域上传'}
          </p>
          <p className="ant-upload-hint">
            {uploadType === 'single' ? '支持单个图片上传' :
             uploadType === 'folder' ? '支持整个文件夹上传' :
             '支持ZIP压缩包上传'}
          </p>
        </Upload.Dragger>
        
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Space>
            <Button
              type="primary"
              onClick={handleUploadClick}
              disabled={fileList.length === 0 || !selectedProjectId || uploading}
              loading={uploading && uploadType !== 'folder'}
            >
              {uploading && uploadType !== 'folder' ? `上传中 ${uploadProgress}%` : '开始上传'}
            </Button>
            
            {uploadType === 'folder' && uploading && (
              <Button 
                type="primary"
                onClick={handleFolderUploadComplete}
              >
                完成上传
              </Button>
            )}
          </Space>
        </div>
        
        {uploading && (
          <Progress percent={uploadProgress} style={{ marginTop: 16 }} />
        )}
      </div>
    );
  };

  return (
    <div style={{ padding: '20px' }}>
      <Title level={2}>批量上传图片</Title>
      
      <Card title="上传设置" style={{ marginBottom: 20 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text strong>选择项目：</Text>
            <Select
              style={{ width: 300 }}
              placeholder="请选择项目"
              onChange={handleProjectChange}
              value={selectedProjectId}
              loading={loadingProjects}
            >
              {projects.map(project => (
                <Option key={project.id} value={project.id}>{project.name}</Option>
              ))}
            </Select>
          </div>
          
          <div>
            <Text strong>上传类型：</Text>
            <Radio.Group onChange={handleUploadTypeChange} value={uploadType}>
              <Radio value="single">单张图片</Radio>
              <Radio value="folder">文件夹</Radio>
              <Radio value="zip">ZIP压缩包</Radio>
            </Radio.Group>
          </div>
        </Space>
      </Card>
      
      <Card title="上传区域" style={{ marginBottom: 20 }}>
        {renderUploadComponent()}
      </Card>
      
      {uploadedImages.length > 0 && (
        <Card title={`上传结果 (${uploadedImages.length}张图片)`}>
          <List
            grid={{ gutter: 16, xs: 1, sm: 2, md: 3, lg: 4, xl: 6, xxl: 8 }}
            dataSource={uploadedImages}
            renderItem={image => (
              <List.Item>
                <Card
                  hoverable
                  cover={
                    <div style={{ height: 150, display: 'flex', justifyContent: 'center', alignItems: 'center', overflow: 'hidden' }}>
                      <Image
                        src={image.file_path.startsWith('http') 
                          ? image.file_path 
                          : `${api.defaults.baseURL}/${image.file_path}`}
                        alt="上传图片"
                        style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                      />
                    </div>
                  }
                >
                  <Card.Meta
                    title={image.file_path.split('/').pop()}
                    description={
                      <div>
                        <p>类型: {image.file_type}</p>
                        {image.width && image.height && (
                          <p>尺寸: {image.width} x {image.height}</p>
                        )}
                      </div>
                    }
                  />
                </Card>
              </List.Item>
            )}
          />
        </Card>
      )}
    </div>
  );
};

export default ImageUpload;
 