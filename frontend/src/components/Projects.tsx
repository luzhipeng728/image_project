import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Space, Popconfirm, message, Progress, Select } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SyncOutlined } from '@ant-design/icons';
import api from '../utils/api';

interface Project {
  id: number;
  name: string;
  description: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
}

interface User {
  username: string;
  created_at: string;
  is_admin: boolean;
}

interface TaskStatus {
  total_tasks: number;
  completed_tasks: number;
  percentage: number;
  status: string;
  tasks?: {
    task_id: string;
    status: string;
    progress: string;
    percentage: number;
    subtasks?: {
      id: string;
      status: string;
      updated_at: string;
    }[];
  }[];
  updated_at?: string;
}

interface BatchGenerateForm {
  prompt: string;
  model_id: string;
}

interface Model {
  id: string;
  name: string;
}

const Projects: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [createModalVisible, setCreateModalVisible] = useState<boolean>(false);
  const [editModalVisible, setEditModalVisible] = useState<boolean>(false);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [form] = Form.useForm();
  const [taskModalVisible, setTaskModalVisible] = useState<boolean>(false);
  const [currentTaskStatus, setCurrentTaskStatus] = useState<TaskStatus | null>(null);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);
  const [batchGenModalVisible, setBatchGenModalVisible] = useState<boolean>(false);
  const [batchGenForm] = Form.useForm();
  const [availableModels, setAvailableModels] = useState<Model[]>([]);

  // 获取当前用户信息
  useEffect(() => {
    const fetchCurrentUser = async () => {
      try {
        const response = await api.get('/api/auth/me');
        setCurrentUser(response.data);
      } catch (error) {
        console.error('获取当前用户信息失败:', error);
      }
    };

    fetchCurrentUser();
  }, []);

  // 获取项目列表
  const fetchProjects = async () => {
    setLoading(true);
    try {
      const response = await api.get('/api/projects/');
      setProjects(response.data);
    } catch (error) {
      console.error('获取项目列表失败:', error);
      message.error('获取项目列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  // 获取可用模型列表
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const response = await api.get('/api/generation/models');
        // 确保返回的模型ID是字符串类型
        const models = response.data.map((model: any) => ({
          ...model,
          id: String(model.id)
        }));
        setAvailableModels(models);
      } catch (error) {
        console.error('获取模型列表失败:', error);
        message.error('获取模型列表失败');
      }
    };
    fetchModels();
  }, []);

  // 创建项目
  const handleCreateProject = async (values: any) => {
    try {
      await api.post('/api/projects/', values);
      message.success('项目创建成功');
      setCreateModalVisible(false);
      form.resetFields();
      fetchProjects();
    } catch (error) {
      console.error('创建项目失败:', error);
      message.error('创建项目失败');
    }
  };

  // 编辑项目
  const handleEditProject = async (values: any) => {
    if (!currentProject) return;
    
    try {
      await api.put(`/api/projects/${currentProject.id}`, values);
      message.success('项目更新成功');
      setEditModalVisible(false);
      form.resetFields();
      fetchProjects();
    } catch (error) {
      console.error('更新项目失败:', error);
      message.error('更新项目失败');
    }
  };

  // 删除项目
  const handleDeleteProject = async (id: number) => {
    try {
      await api.delete(`/api/projects/${id}`);
      message.success('项目删除成功');
      fetchProjects();
    } catch (error) {
      console.error('删除项目失败:', error);
      message.error('删除项目失败');
    }
  };

  // 打开编辑项目模态框
  const showEditModal = (project: Project) => {
    setCurrentProject(project);
    form.setFieldsValue({
      name: project.name,
      description: project.description
    });
    setEditModalVisible(true);
  };

  // 检查项目是否有运行中的任务 - 使用新的Redis进度API
  const checkProjectHasRunningTask = async (projectId: number): Promise<boolean> => {
    try {
      const response = await api.get(`/api/generation/project/${projectId}/progress`);
      // 如果获取到了进度信息，且状态为processing，则认为有运行中的任务
      return response.data.status === 'processing';
    } catch (error) {
      console.error('检查项目任务状态失败:', error);
      // 如果无法获取状态信息，默认为没有运行中的任务
      return false;
    }
  };

  // 修改批量重新生成函数 - 使用新的任务创建API
  const handleBatchRegenerate = async (projectId: number) => {
    try {
      // 先检查是否有运行中的任务
      const hasRunningTask = await checkProjectHasRunningTask(projectId);
      if (hasRunningTask) {
        message.error('该项目已存在未完成的批量任务，请等待当前任务完成');
        // return;
      }

      const values = await batchGenForm.validateFields();
      
      // 使用新的API创建任务
      await api.post('/api/generation/project/task', {
        project_id: projectId,
        prompt: values.prompt,
        model_id: values.model_id
      });
      
      message.success('批量处理任务已启动');
      setBatchGenModalVisible(false);
      setTaskModalVisible(true);
      
      // 开始轮询任务进度
      startPolling(projectId);
    } catch (error) {
      console.error('批量重新生成失败:', error);
      message.error('批量重新生成失败');
    }
  };

  // 修改轮询任务状态的函数 - 使用新的进度API
  const startPolling = (projectId: number) => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
    }

    // 立即执行一次获取进度
    fetchTaskProgress(projectId);

    const interval = setInterval(async () => {
      try {
        await fetchTaskProgress(projectId);

        // 如果当前任务状态是completed或no_tasks，停止轮询
        if (currentTaskStatus?.status === 'completed' || currentTaskStatus?.status === 'no_tasks') {
          clearInterval(interval);
          setPollingInterval(null);
          // 任务完成后刷新项目列表
          fetchProjects();
        }
      } catch (error) {
        console.error('获取任务状态失败:', error);
      }
    }, 3000); // 每3秒轮询一次

    setPollingInterval(interval);
  };

  // 获取任务进度
  const fetchTaskProgress = async (projectId: number) => {
    try {
      const response = await api.get(`/api/generation/project/${projectId}/progress`);
      setCurrentTaskStatus(response.data);
      return response.data;
    } catch (error) {
      console.error('获取任务进度失败:', error);
      return null;
    }
  };

  // 关闭任务模态框时清除轮询
  const handleCloseTaskModal = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
    setTaskModalVisible(false);
  };

  // 开始批量生成
  const showBatchGenModal = (project: Project) => {
    setCurrentProject(project);
    setBatchGenModalVisible(true);
    // 设置默认值，确保model_id是字符串类型
    batchGenForm.setFieldsValue({
      prompt: '请根据图片生成图片的描述，要求描述清晰，描述内容要包含图片的全部内容，不要遗漏任何细节',
      model_id: availableModels[0]?.id || ''
    });
  };

  // 表格列定义
  const columns = [
    {
      title: '项目名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: '创建者',
      dataIndex: 'owner_id',
      key: 'owner_id',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text: string) => new Date(text).toLocaleString()
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Project) => (
        <Space size="middle">
          <Button 
            icon={<EditOutlined />} 
            onClick={() => showEditModal(record)}
            disabled={currentUser?.username !== record.owner_id && !currentUser?.is_admin}
          >
            编辑
          </Button>
          <Button
            icon={<SyncOutlined />}
            onClick={() => showBatchGenModal(record)}
            disabled={currentUser?.username !== record.owner_id && !currentUser?.is_admin}
          >
            批量重新生成
          </Button>
          {(currentUser?.is_admin || currentUser?.username === record.owner_id) && (
            <Popconfirm
              title="确定要删除这个项目吗?"
              onConfirm={() => handleDeleteProject(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button danger icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '20px' }}>
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
        <h1>项目管理</h1>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          onClick={() => setCreateModalVisible(true)}
        >
          创建项目
        </Button>
      </div>

      <Table 
        columns={columns} 
        dataSource={projects} 
        rowKey="id" 
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      {/* 创建项目模态框 */}
      <Modal
        title="创建新项目"
        visible={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        footer={null}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateProject}
        >
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="请输入项目名称" />
          </Form.Item>
          <Form.Item
            name="description"
            label="项目描述"
          >
            <Input.TextArea placeholder="请输入项目描述" rows={4} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              创建
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑项目模态框 */}
      <Modal
        title="编辑项目"
        visible={editModalVisible}
        onCancel={() => setEditModalVisible(false)}
        footer={null}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleEditProject}
        >
          <Form.Item
            name="name"
            label="项目名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="请输入项目名称" />
          </Form.Item>
          <Form.Item
            name="description"
            label="项目描述"
          >
            <Input.TextArea placeholder="请输入项目描述" rows={4} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              保存
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 批量生成模态框 */}
      <Modal
        title="批量重新生成图片"
        visible={batchGenModalVisible}
        onCancel={() => setBatchGenModalVisible(false)}
        footer={null}
      >
        <Form
          form={batchGenForm}
          layout="vertical"
          onFinish={() => handleBatchRegenerate(currentProject?.id || 0)}
        >
          <Form.Item
            name="prompt"
            label="图片描述"
            rules={[{ required: true, message: '请输入图片描述' }]}
          >
            <Input.TextArea 
              placeholder="请描述你想要的图片风格和内容" 
              rows={4}
            />
          </Form.Item>
          <Form.Item
            name="model_id"
            label="选择模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select>
              {availableModels.map(model => (
                <Select.Option key={model.id} value={model.id}>
                  {model.name}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              开始生成
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 任务进度模态框 - 适配新的Redis进度API */}
      <Modal
        title="生成进度"
        visible={taskModalVisible}
        onCancel={handleCloseTaskModal}
        footer={[
          <Button key="close" onClick={handleCloseTaskModal}>
            关闭
          </Button>
        ]}
      >
        {currentTaskStatus ? (
          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8 }}>
              总体进度: {currentTaskStatus.status}
              {currentTaskStatus.status === 'no_tasks' && 
                <span> - 没有找到任务信息</span>
              }
            </div>
            
            <Progress
              percent={currentTaskStatus.percentage || 0}
              status={
                currentTaskStatus.status === 'completed' ? 'success' :
                currentTaskStatus.status === 'failed' ? 'exception' :
                currentTaskStatus.status === 'no_tasks' ? 'exception' :
                'active'
              }
            />
            
            <div style={{ marginBottom: 16 }}>
              进度: {currentTaskStatus.completed_tasks} / {currentTaskStatus.total_tasks} 个任务
            </div>
            
            {/* 显示各个任务的进度 */}
            {currentTaskStatus.tasks && currentTaskStatus.tasks.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <h4>任务详情</h4>
                {currentTaskStatus.tasks.map((task) => (
                  <div key={task.task_id} style={{ marginBottom: 8, padding: 8, backgroundColor: '#f5f5f5', borderRadius: 4 }}>
                    <div>任务 {task.task_id}: {task.status}</div>
                    <Progress size="small" percent={task.percentage} />
                    <div>进度: {task.progress}</div>
                  </div>
                ))}
              </div>
            )}
            
            {currentTaskStatus.updated_at && (
              <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
                最后更新: {new Date(currentTaskStatus.updated_at).toLocaleString()}
              </div>
            )}
          </div>
        ) : (
          <div>正在获取任务进度...</div>
        )}
      </Modal>
    </div>
  );
};

export default Projects;