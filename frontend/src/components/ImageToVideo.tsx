import React, { useState, useEffect, useCallback } from 'react';
import { 
  Row, 
  Col, 
  Card, 
  Upload, 
  Button, 
  Input, 
  Form, 
  Progress, 
  List, 
  Typography, 
  Space, 
  Divider, 
  message, 
  Spin,
  Tag,
  Alert,
  Tooltip
} from 'antd';
import { 
  UploadOutlined, 
  PlayCircleOutlined, 
  ClockCircleOutlined, 
  DeleteOutlined, 
  DownloadOutlined,
  ReloadOutlined,
  SyncOutlined
} from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd/es/upload/interface';
import api, { 
  createVideoGeneration, 
  getVideoTaskStatus, 
  getUserVideoTasks,
  VideoTaskStatus,
  BACKEND_URL
} from '../utils/api';

const { TextArea } = Input;
const { Title, Text } = Typography;

interface VideoHistoryItem {
  id: number;
  status: 'pending' | 'queued' | 'initializing' | 'loading_model' | 'preparing_environment' | 'setting_parameters' |
         'loading_image' | 'preprocessing_image' | 'configuring_model' | 'preparing_prompt' | 'setting_sampler' |
         'configuring_scheduler' | 'preparing_inference' | 'inference' | 'postprocessing_frames' | 'preparing_video' |
         'combining_video' | 'optimizing_video' | 'postprocessing_video' | 'completed' | 'processing' | 'failed';
  thumbnail: string;
  video_path: string | null;
  prompt: string;
  created_at: string;
  progress: number;
  estimated_time: number | null;
  error_message: string | null;
  thumbnailUrl?: string;
  node_id?: string;
  node_status?: string;
  node_description?: string;
  queue_position?: number;
}

const ImageToVideo: React.FC = () => {
  const [form] = Form.useForm();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [previewImage, setPreviewImage] = useState<string>('');
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<string>('');
  const [progress, setProgress] = useState<number>(0);
  const [remainingTime, setRemainingTime] = useState<number>(0);
  const [videoHistory, setVideoHistory] = useState<VideoHistoryItem[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<number | null>(null);
  const [username, setUsername] = useState<string>('');
  const [localImagePath, setLocalImagePath] = useState<string>('');

  // 获取视频缩略图
  const getVideoThumbnail = (videoPath: string | null, itemId: number): string => {
    // console.log('获取视频缩略图:', videoPath, itemId);
    if (!videoPath) return 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYwIiBoZWlnaHQ9IjkwIiB2aWV3Qm94PSIwIDAgMTYwIDkwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8cmVjdCB3aWR0aD0iMTYwIiBoZWlnaHQ9IjkwIiBmaWxsPSIjRTZFNkU2Ii8+CjxwYXRoIGQ9Ik03MC41IDQwLjVMOTcuNSA1OC41VjIyLjVMNzAuNSA0MC41WiIgc3Ryb2tlPSIjOTk5OTk5IiBzdHJva2Utd2lkdGg9IjMiLz4KPGNpcmNsZSBjeD0iODAiIGN5PSI0NSIgcj0iMjAiIHN0cm9rZT0iIzk5OTk5OSIgc3Ryb2tlLXdpZHRoPSIzIi8+Cjwvc3ZnPgo=';
    // 查找历史记录中是否已经有缩略图
    const historyItem = videoHistory.find(item => item.id === itemId);
    if (historyItem && historyItem.thumbnailUrl) {
      return historyItem.thumbnailUrl;
    }
    
    // 使用默认缩略图，但标记为需要生成
    setTimeout(() => {
      generateVideoThumbnailSafe(videoPath, itemId);
    }, 100);
    
    // 返回默认图片
    return 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYwIiBoZWlnaHQ9IjkwIiB2aWV3Qm94PSIwIDAgMTYwIDkwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8cmVjdCB3aWR0aD0iMTYwIiBoZWlnaHQ9IjkwIiBmaWxsPSIjRTZFNkU2Ii8+CjxwYXRoIGQ9Ik03MC41IDQwLjVMOTcuNSA1OC41VjIyLjVMNzAuNSA0MC41WiIgc3Ryb2tlPSIjOTk5OTk5IiBzdHJva2Utd2lkdGg9IjMiLz4KPGNpcmNsZSBjeD0iODAiIGN5PSI0NSIgcj0iMjAiIHN0cm9rZT0iIzk5OTk5OSIgc3Ryb2tlLXdpZHRoPSIzIi8+Cjwvc3ZnPgo=';
  };

  // 安全地生成视频缩略图（避免CORS问题）
  const generateVideoThumbnailSafe = (videoPath: string | null, itemId: number) => {
    if (!videoPath) return;
    
    // 使用代理URL来避免CORS问题
    // const videoProxyUrl = getVideoProxyUrl(videoPath);
    
    // 尝试通过后端代理获取视频第一帧作为缩略图
    // 由于前端直接生成可能会遇到CORS问题，这里只更新一个预设的缩略图
    const colorMap: {[key: number]: string} = {
      0: '#FFD700', // 金色
      1: '#7FFFD4', // 碧绿色
      2: '#FF6347', // 番茄色
      3: '#9370DB', // 中紫色
      4: '#3CB371', // 中海绿色
      5: '#4682B4', // 钢青色
      6: '#D2691E', // 巧克力色
      7: '#8A2BE2', // 紫罗兰色
      8: '#2E8B57', // 海绿色
      9: '#4169E1'  // 皇家蓝
    };
    
    // 基于itemId选择一个颜色
    const colorIndex = itemId % 10;
    const bgColor = colorMap[colorIndex] || '#4169E1';
    
    // 创建一个简单的带视频图标和背景色的SVG缩略图
    const thumbnailSvg = `
      <svg width="320" height="180" xmlns="http://www.w3.org/2000/svg">
        <rect width="320" height="180" fill="${bgColor}" />
        <circle cx="160" cy="90" r="40" fill="white" opacity="0.8" />
        <polygon points="145,70 145,110 185,90" fill="${bgColor}" />
        <text x="160" y="150" text-anchor="middle" fill="white" font-family="Arial" font-weight="bold">视频 #${itemId}</text>
      </svg>
    `;
    
    // 将SVG转为base64
    const thumbnailUrl = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(thumbnailSvg)));
    
    // 更新历史记录中的缩略图
    setVideoHistory(prevHistory => 
      prevHistory.map(item => 
        item.id === itemId 
          ? { ...item, thumbnailUrl } 
          : item
      )
    );
  };
  


  // 更新视频历史并生成缩略图
  const updateVideoHistoryWithThumbnails = useCallback((tasks: any[]) => {
    const formattedHistory = tasks.map((task: any) => ({
      id: task.id,
      status: task.status,
      thumbnail: '', // 后端没有提供缩略图，可以考虑使用图片ID获取
      video_path: task.video_path,
      prompt: task.prompt,
      created_at: task.created_at,
      progress: task.progress,
      estimated_time: task.estimated_time,
      error_message: task.error_message,
      thumbnailUrl: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYwIiBoZWlnaHQ9IjkwIiB2aWV3Qm94PSIwIDAgMTYwIDkwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPgo8cmVjdCB3aWR0aD0iMTYwIiBoZWlnaHQ9IjkwIiBmaWxsPSIjRTZFNkU2Ii8+CjxwYXRoIGQ9Ik03MC41IDQwLjVMOTcuNSA1OC41VjIyLjVMNzAuNSA0MC41WiIgc3Ryb2tlPSIjOTk5OTk5IiBzdHJva2Utd2lkdGg9IjMiLz4KPGNpcmNsZSBjeD0iODAiIGN5PSI0NSIgcj0iMjAiIHN0cm9rZT0iIzk5OTk5OSIgc3Ryb2tlLXdpZHRoPSIzIi8+Cjwvc3ZnPgo=', // 使用默认占位图，等待生成真正的视频缩略图
      node_id: task.node_id,
      node_status: task.node_status,
      node_description: task.node_description,
      queue_position: task.queue_position
    }));
    
    setVideoHistory(formattedHistory);
    
    // 对已完成的视频生成缩略图
    formattedHistory.forEach(item => {
      if (item.status === 'completed' && item.video_path) {
        setTimeout(() => {
          generateVideoThumbnailSafe(item.video_path, item.id);
        }, 100);
      }
    });
  }, []);

  // 获取视频生成历史
  const fetchVideoHistory = useCallback(async () => {
    try {
      const tasks = await getUserVideoTasks();
      updateVideoHistoryWithThumbnails(tasks);
    } catch (error) {
      console.error('获取视频历史失败:', error);
      message.error('获取视频历史失败');
    }
  }, [updateVideoHistoryWithThumbnails]);

  // 更新单个任务状态
  const updateTaskStatus = useCallback(async (taskId: number) => {
    try {
      const status = await getVideoTaskStatus(taskId);
      
      // 更新历史记录中的任务状态
      setVideoHistory(prevHistory => 
        prevHistory.map(item => 
          item.id === taskId 
            ? { 
                ...item, 
                status: status.status, 
                progress: status.progress,
                estimated_time: status.estimated_time,
                video_path: status.video_path,
                error_message: status.error_message,
                node_id: status.node_id,
                node_status: status.node_status,
                node_description: status.node_description,
                queue_position: status.queue_position
              } 
            : item
        )
      );
      
      // 如果是当前正在关注的任务，也更新主界面状态
      if (currentTaskId === taskId) {
        setProgress(status.progress);
        setRemainingTime(status.estimated_time || 0);
        
        // 更新当前步骤显示，优先使用节点描述
        if (status.node_description) {
          setCurrentStep(`${status.node_description} (${status.progress}%)`);
        } else if (status.status === 'queued' && status.queue_position) {
          setCurrentStep(`排队中 (位置: ${status.queue_position})`);
        } else {
          setCurrentStep(`处理中 (${status.progress}%)`);
        }
        
        if (status.status === 'completed' || status.status === 'failed') {
          // 任务已完成或失败，更新UI
          if (status.status === 'completed') {
            setIsGenerating(false);
            setCurrentStep('生成完成');
            if (status.video_path) {
              setVideoUrl(status.video_path);
            }
          } else {
            setIsGenerating(false);
            setCurrentStep(`生成失败: ${status.error_message || '未知错误'}`);
            message.error(`视频生成失败: ${status.error_message || '未知错误'}`);
          }
          
          // 重置当前任务ID
          setCurrentTaskId(null);
          // 刷新历史记录
          fetchVideoHistory();
        }
      }
    } catch (error) {
      console.error(`获取任务 ${taskId} 状态失败:`, error);
    }
  }, [currentTaskId, fetchVideoHistory]);

  // 播放历史视频
  const playHistoryVideo = (item: VideoHistoryItem) => {
    if (item.video_path) {
      // 使用代理URL避免CORS问题
      // const fullVideoUrl = getVideoProxyUrl(item.video_path);
      
      // console.log('播放视频:', item.video_path);
      setVideoUrl(item.video_path);
      
      // 滚动到视频预览区域
      const videoPreviewElement = document.querySelector('.video-preview-card');
      if (videoPreviewElement) {
        videoPreviewElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } else {
      message.warning('视频尚未生成完成');
    }
  };

  // 格式化剩余时间
  const formatRemainingTime = (seconds: number): string => {
    if (!seconds || seconds <= 0) return '计算中...';
    
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    
    return `${minutes}分${remainingSeconds}秒`;
  };

  // 获取当前用户名
  useEffect(() => {
    const storedUsername = localStorage.getItem('username');
    if (storedUsername) {
      setUsername(storedUsername);
    }
    
    // 页面加载时获取历史记录
    fetchVideoHistory();
  }, [fetchVideoHistory]);

  // 轮询当前任务状态
  useEffect(() => {
    if (currentTaskId && isGenerating) {
      const intervalId = setInterval(() => {
        updateTaskStatus(currentTaskId);
      }, 2000);
      
      return () => clearInterval(intervalId);
    }
  }, [currentTaskId, isGenerating, updateTaskStatus]);

  // 自动获取最新未完成视频的进度
  useEffect(() => {
    // 如果已经在生成视频，不需要再监控其他任务
    if (isGenerating && currentTaskId) return;
    
    // 找出最新的未完成视频任务
    const pendingTasks = videoHistory.filter(
      task => task.status === 'pending' || task.status === 'processing'
    );
    
    if (pendingTasks.length > 0) {
      // 按创建时间排序，获取最新的任务
      const latestTask = pendingTasks.sort((a, b) => 
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )[0];
      
      // 设置当前任务ID并开始轮询
      setCurrentTaskId(latestTask.id);
      setIsGenerating(true);
      setProgress(latestTask.progress || 0);
      setRemainingTime(latestTask.estimated_time || 0);
      setCurrentStep(`处理中 (${latestTask.progress || 0}%)`);
    }
  }, [videoHistory, isGenerating, currentTaskId]);

  // 定期刷新历史记录
  useEffect(() => {
    // 每10秒刷新一次历史记录
    const intervalId = setInterval(() => {
      fetchVideoHistory();
    }, 10000); // 从30秒改为10秒
    
    return () => clearInterval(intervalId);
  }, [fetchVideoHistory]);

  // 轮询所有处理中的任务状态
  useEffect(() => {
    // 找出所有处理中的任务
    const processingTasks = videoHistory.filter(task => task.status === 'processing');
    
    if (processingTasks.length > 0) {
      // 为每个处理中的任务创建轮询
      const intervalId = setInterval(() => {
        // 更新所有处理中任务的状态
        processingTasks.forEach(task => {
          updateTaskStatus(task.id);
        });
      }, 5000); // 每5秒更新一次
      
      return () => clearInterval(intervalId);
    }
  }, [videoHistory, updateTaskStatus]);

  // 处理图片上传
  const handleUploadChange: UploadProps['onChange'] = ({ fileList: newFileList }) => {
    setFileList(newFileList);
    if (newFileList.length > 0 && newFileList[0].originFileObj) {
      const reader = new FileReader();
      reader.onload = () => {
        const imageDataUrl = reader.result as string;
        setPreviewImage(imageDataUrl);
        // 保存本地图片数据
        setLocalImagePath(imageDataUrl);
      };
      reader.readAsDataURL(newFileList[0].originFileObj);
    } else {
      setPreviewImage('');
      setLocalImagePath('');
    }
  };

  // 处理表单提交
  const handleSubmit = async (values: any) => {
    if (fileList.length === 0 || !localImagePath) {
      message.error('请先上传图片');
      return;
    }

    try {
      setIsGenerating(true);
      setProgress(0);
      setCurrentStep('创建视频生成任务...');
      
      // 直接使用本地图片的 base64 数据
      const imageBase64 = localImagePath.split(',')[1]; // 移除 "data:image/jpeg;base64," 前缀
      
      // 创建视频生成任务，使用 image_base64 参数而不是 image_id
      const result = await createVideoGeneration({
        image_base64: imageBase64, // 使用 base64 编码的图片数据
        prompt: values.prompt,
        steps: 10, // 可以从表单获取
        num_frames: 81 // 可以从表单获取
      });
      
      // 设置当前任务ID，开始轮询状态
      setCurrentTaskId(result.task_id);
      setCurrentStep('初始化生成任务');
      
    } catch (error) {
      console.error('创建视频生成任务失败:', error);
      message.error('创建视频生成任务失败');
      setIsGenerating(false);
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <Row gutter={[16, 16]}>
        {/* 左侧：上传图片和提示词 */}
        <Col xs={24} md={6}>
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Card title="上传图片">
              <div style={{ textAlign: 'center' }}>
                <Upload
                  listType="picture-card"
                  fileList={fileList}
                  onChange={handleUploadChange}
                  beforeUpload={() => false}
                  maxCount={1}
                >
                  {fileList.length === 0 && <div>
                    <UploadOutlined />
                    <div style={{ marginTop: 8 }}>点击上传</div>
                  </div>}
                </Upload>
                {previewImage && (
                  <div style={{ marginTop: 16 }}>
                    <img 
                      src={previewImage} 
                      alt="预览图片" 
                      style={{ maxWidth: '100%', maxHeight: '200px' }} 
                    />
                  </div>
                )}
              </div>
            </Card>

            <Card title="提示词">
              <Form form={form} onFinish={handleSubmit} layout="vertical">
                <Form.Item
                  name="prompt"
                  rules={[{ required: true, message: '请输入提示词' }]}
                >
                  <TextArea 
                    rows={4} 
                    placeholder="描述您希望生成的视频内容..." 
                    disabled={isGenerating}
                  />
                </Form.Item>
                <Form.Item>
                  <Button 
                    type="primary" 
                    htmlType="submit" 
                    icon={<PlayCircleOutlined />} 
                    loading={isGenerating}
                    block
                  >
                    {isGenerating ? '生成中...' : '开始生成'}
                  </Button>
                </Form.Item>
              </Form>
            </Card>
          </Space>
        </Col>

        {/* 中间：视频预览 */}
        <Col xs={24} md={12}>
          <Card 
            className="video-preview-card"
            title={
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>视频预览</span>
              </div>
            } 
            style={{ height: '100%' }}
            extra={
              isGenerating && (
                <Tooltip title="刷新状态">
                  <Button 
                    type="text" 
                    icon={<ReloadOutlined />} 
                    onClick={() => currentTaskId && updateTaskStatus(currentTaskId)} 
                  />
                </Tooltip>
              )
            }
          >
            <div style={{ textAlign: 'center' }}>
              {videoUrl ? (
                <div style={{ marginBottom: 16 }}>
                  <video 
                    controls 
                    autoPlay
                    style={{ 
                      width: '100%', 
                      maxHeight: '400px', 
                      borderRadius: '8px', 
                      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                      backgroundColor: '#000'
                    }}
                    src={videoUrl}
                  />
                </div>
              ) : (
                <div 
                  style={{ 
                    height: '300px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    background: '#f5f5f5',
                    borderRadius: '8px',
                    marginBottom: 16
                  }}
                >
                  <div style={{ textAlign: 'center' }}>
                    <PlayCircleOutlined style={{ fontSize: 48, color: '#d9d9d9', marginBottom: 16 }} />
                    <br />
                    <Text type="secondary">视频将在这里显示</Text>
                  </div>
                </div>
              )}
            </div>
            {/* {isGenerating && (
              <div style={{ marginTop: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span>{currentStep}</span>
                  <span>{formatRemainingTime(remainingTime)}</span>
                </div>
                <Progress 
                  percent={progress} 
                  status="active" 
                  strokeColor={{
                    '0%': '#108ee9',
                    '100%': '#87d068',
                  }}
                />
                
                {videoHistory.find(item => item.id === currentTaskId)?.node_description && (
                  <Alert
                    message={videoHistory.find(item => item.id === currentTaskId)?.node_description}
                    type="info"
                    showIcon
                    style={{ marginTop: 16 }}
                  />
                )}
                
                {videoHistory.find(item => item.id === currentTaskId)?.status === 'queued' && (
                  <Alert
                    message={`排队中 (位置: ${videoHistory.find(item => item.id === currentTaskId)?.queue_position || '等待中'})`}
                    type="warning"
                    showIcon
                    style={{ marginTop: 16 }}
                  />
                )}
              </div>
            )} */}
          </Card>
        </Col>

        {/* 右侧：历史记录 */}
        <Col xs={24} md={6}>
          <Card 
            title="生成历史" 
            style={{ height: '100%' }}
            extra={
              <Tooltip title="刷新历史">
                <Button 
                  type="text" 
                  icon={<ReloadOutlined />} 
                  onClick={fetchVideoHistory} 
                />
              </Tooltip>
            }
            bodyStyle={{ padding: '0 16px', height: 'calc(100vh - 220px)', overflow: 'hidden' }}
          >
            <List
              itemLayout="vertical"
              dataSource={videoHistory}
              style={{ 
                height: '100%', 
                overflowY: 'auto', 
                paddingRight: '8px' 
              }}
              renderItem={(item) => (
                <List.Item>
                  {item.status === 'completed' && item.video_path && (
                    <div 
                      style={{ 
                        position: 'relative', 
                        marginBottom: 12,
                        cursor: 'pointer',
                        borderRadius: '8px',
                        overflow: 'hidden'
                      }}
                      onClick={() => playHistoryVideo(item)}
                    >
                      <div 
                        style={{ 
                          width: '100%', 
                          height: '120px', 
                          background: '#f0f0f0',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}
                      >
                        <img 
                          src={getVideoThumbnail(item.video_path, item.id)} 
                          alt="视频封面" 
                          style={{ 
                            width: '100%', 
                            height: '100%', 
                            objectFit: 'cover' 
                          }} 
                        />
                        <div 
                          style={{ 
                            position: 'absolute', 
                            top: 0, 
                            left: 0, 
                            width: '100%', 
                            height: '100%', 
                            background: 'rgba(0,0,0,0.3)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                          }}
                        >
                          <PlayCircleOutlined style={{ fontSize: 48, color: 'white' }} />
                        </div>
                      </div>
                    </div>
                  )}
                  <List.Item.Meta
                    title={
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Text ellipsis style={{ maxWidth: '80%' }}>{item.prompt}</Text>
                        {item.status === 'pending' && <Tag color="default" style={{ marginLeft: 8 }}>等待中</Tag>}
                        {item.status === 'queued' && (
                          <Tag color="warning" style={{ marginLeft: 8 }}>
                            <SyncOutlined spin /> 队列中 {item.queue_position ? `(${item.queue_position})` : ''}
                          </Tag>
                        )}
                        {(item.status === 'processing' || 
                          ['initializing', 'loading_model', 'preparing_environment', 'setting_parameters',
                           'loading_image', 'preprocessing_image', 'configuring_model', 'preparing_prompt', 
                           'setting_sampler', 'configuring_scheduler', 'preparing_inference'].includes(item.status)) && (
                          <Tag color="processing" style={{ marginLeft: 8 }}> 
                            <SyncOutlined spin /> {item.node_description || '准备中'}
                          </Tag>
                        )}
                        {item.status === 'inference' && (
                          <Tag color="processing" style={{ marginLeft: 8 }}> 
                            <SyncOutlined spin /> 视频生成中
                          </Tag>
                        )}
                        {(item.status === 'postprocessing_frames' || 
                          item.status === 'preparing_video' || 
                          item.status === 'combining_video' || 
                          item.status === 'optimizing_video' || 
                          item.status === 'postprocessing_video') && (
                          <Tag color="processing" style={{ marginLeft: 8 }}> 
                            <SyncOutlined spin /> {item.node_description || '视频处理中'}
                          </Tag>
                        )}
                        {item.status === 'completed' && <Tag color="success" style={{ marginLeft: 8 }}>已完成</Tag>}
                        {item.status === 'failed' && <Tag color="error" style={{ marginLeft: 8 }}>失败</Tag>}
                      </div>
                    }
                    description={
                      <Space direction="vertical" size={0} style={{ width: '100%' }}>
                        <Text type="secondary">{new Date(item.created_at).toLocaleString()}</Text>
                        {(item.status === 'processing' || 
                         item.status === 'inference' || 
                         item.status === 'combining_video' ||
                         ['initializing', 'loading_model', 'preparing_environment', 'setting_parameters',
                          'loading_image', 'preprocessing_image', 'configuring_model', 'preparing_prompt', 
                          'setting_sampler', 'configuring_scheduler', 'preparing_inference',
                          'postprocessing_frames', 'preparing_video', 'optimizing_video', 
                          'postprocessing_video'].includes(item.status)) && (
                          <>
                            <Progress percent={item.progress} size="small" status="active" />
                            {item.node_description && (
                              <Text type="secondary">
                                当前阶段: {item.node_description}
                              </Text>
                            )}
                            <Text type="secondary">
                              预计剩余: {formatRemainingTime(item.estimated_time || 0)}
                            </Text>
                          </>
                        )}
                        {item.status === 'queued' && (
                          <Text type="warning">
                            队列位置: {item.queue_position || '等待中'}
                          </Text>
                        )}
                        {item.status === 'failed' && (
                          <Text type="danger" ellipsis style={{ maxWidth: '100%' }}>
                            {item.error_message || '未知错误'}
                          </Text>
                        )}
                      </Space>
                    }
                  />
                  <div style={{ marginTop: 8 }}>
                    {item.status === 'completed' && (
                      <Space>
                        <Button 
                          type="primary" 
                          size="small" 
                          icon={<PlayCircleOutlined />} 
                          onClick={() => playHistoryVideo(item)}
                        >
                          播放
                        </Button>
                        <Button 
                          size="small" 
                          icon={<DownloadOutlined />} 
                          href={item.video_path ? item.video_path : undefined}
                          target="_blank"
                        >
                          下载
                        </Button>
                      </Space>
                    )}
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ImageToVideo; 