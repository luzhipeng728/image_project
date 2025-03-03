import React, { useState, useEffect } from 'react';
import { Layout, Menu, Card, Form, Input, Button, Select, InputNumber, Switch, message, List, Tag } from 'antd';
import { UserOutlined, LogoutOutlined, HistoryOutlined, SwapOutlined, ProjectOutlined, UploadOutlined, PictureOutlined, VideoCameraOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import api from '../utils/api';
import ImageToImage from './ImageToImage';
import History from './History';
import Projects from './Projects';
import ImageUpload from './ImageUpload';
import ProjectGallery from './ProjectGallery';
import ImageToVideo from './ImageToVideo';

const { Header, Content, Sider } = Layout;
const { Option } = Select;
const { TextArea } = Input;

interface Model {
  id: number;
  name: string;
  alias: string;
  price: number;
}

interface GenerationForm {
  prompt: string;
  model_id: number;
  seed?: number;
  width: number;
  height: number;
  enhance: boolean;
}

interface HistoryResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  records: HistoryItem[];
}

interface HistoryItem {
  id: number;
  prompt: string;
  model_name: string;
  model_alias: string;
  seed: number;
  width: number;
  height: number;
  enhance: boolean;
  result_image_path: string;
  created_at: string;
  generation_type: 'text_to_image' | 'image_to_image';
  source_image_path: string | null;
  enhanced_prompt: string | null;
  status: string;
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(false);
  const [generatedImage, setGeneratedImage] = useState<string>('');
  const [selectedMenu, setSelectedMenu] = useState('playground');

  useEffect(() => {
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const response = await api.get('/api/generation/models');
      setModels(response.data);
      console.log('Models:', response.data);
    } catch (error) {
      console.error('Error fetching models:', error);
      message.error('获取模型列表失败');
    }
  };

  const onGenerate = async (values: GenerationForm) => {
    try {
      setLoading(true);
      const response = await api.post('/api/generation/text-to-image', {
        ...values,
        seed: values.seed || 42,
        width: values.width || 1024,
        height: values.height || 1024,
        enhance: values.enhance || false,
      });
      setGeneratedImage(response.data.image_url);
      message.success('生成成功');
    } catch (error) {
      console.error('Generation error:', error);
      message.error('生成失败');
    } finally {
      setLoading(false);
    }
  };

  const onLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const handleMenuClick = (key: string) => {
    setSelectedMenu(key);
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ color: 'white', fontSize: '20px' }}>图片生成服务</div>
        <Button type="text" icon={<LogoutOutlined />} onClick={onLogout} style={{ color: 'white' }}>
          退出登录
        </Button>
      </Header>
      <Layout>
        <Sider width={200}>
          <Menu
            mode="inline"
            selectedKeys={[selectedMenu]}
            style={{ height: '100%' }}
            onSelect={({ key }) => handleMenuClick(key)}
          >
            <Menu.Item key="playground" icon={<UserOutlined />}>
              文生图
            </Menu.Item>
            <Menu.Item key="image-to-image" icon={<SwapOutlined />}>
              图生图
            </Menu.Item>
            <Menu.Item key="image-to-video" icon={<VideoCameraOutlined />}>
              图生视频
            </Menu.Item>
            <Menu.Item key="history" icon={<HistoryOutlined />}>
              生成历史
            </Menu.Item>
            <Menu.Item key="projects" icon={<ProjectOutlined />}>
              项目管理
            </Menu.Item>
            <Menu.Item key="image-upload" icon={<UploadOutlined />}>
              批量上传
            </Menu.Item>
            <Menu.Item key="project-gallery" icon={<PictureOutlined />}>
              项目图库
            </Menu.Item>
          </Menu>
        </Sider>
        <Content style={{ padding: '24px', minHeight: 280 }}>
          {selectedMenu === 'playground' && (
            <Card title="文生图">
              <Form onFinish={onGenerate} layout="vertical">
                <Form.Item
                  name="model_id"
                  label="选择模型"
                  rules={[{ required: true, message: '请选择模型' }]}
                >
                  <Select placeholder="请选择模型">
                    {models.map(model => (
                      <Option key={model.id} value={model.id}>
                        {model.alias}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
                <Form.Item
                  name="prompt"
                  label="提示词"
                  rules={[{ required: true, message: '请输入提示词' }]}
                >
                  <TextArea rows={4} placeholder="请输入提示词" />
                </Form.Item>
                <Form.Item name="seed" label="种子值">
                  <InputNumber style={{ width: '100%' }} placeholder="随机种子值（可选）" />
                </Form.Item>
                <Form.Item label="图片尺寸" style={{ marginBottom: 0 }}>
                  <Form.Item
                    name="width"
                    initialValue={1024}
                    style={{ display: 'inline-block', width: 'calc(50% - 8px)' }}
                  >
                    <InputNumber
                      min={64}
                      max={2048}
                      placeholder="宽度"
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                  <Form.Item
                    name="height"
                    initialValue={1024}
                    style={{ display: 'inline-block', width: 'calc(50% - 8px)', margin: '0 8px' }}
                  >
                    <InputNumber
                      min={64}
                      max={2048}
                      placeholder="高度"
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Form.Item>
                <Form.Item name="enhance" label="提示词优化" valuePropName="checked" initialValue={false}>
                  <Switch />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" htmlType="submit" loading={loading} block>
                    生成图片
                  </Button>
                </Form.Item>
              </Form>
              {generatedImage && (
                <div style={{ marginTop: 16, textAlign: 'center' }}>
                  <img src={generatedImage} alt="生成的图片" style={{ maxWidth: '100%' }} />
                </div>
              )}
            </Card>
          )}
          {selectedMenu === 'image-to-image' && (
            <Card title="图生图">
              <ImageToImage />
            </Card>
          )}
          {selectedMenu === 'image-to-video' && (
            <Card title="图生视频">
              <ImageToVideo />
            </Card>
          )}
          {selectedMenu === 'history' && <History />}
          {selectedMenu === 'projects' && <Projects />}
          {selectedMenu === 'image-upload' && <ImageUpload />}
          {selectedMenu === 'project-gallery' && <ProjectGallery />}
        </Content>
      </Layout>
    </Layout>
  );
};

export default Dashboard; 