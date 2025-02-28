import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Space, Popconfirm, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
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

const Projects: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [createModalVisible, setCreateModalVisible] = useState<boolean>(false);
  const [editModalVisible, setEditModalVisible] = useState<boolean>(false);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [form] = Form.useForm();

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
    </div>
  );
};

export default Projects; 