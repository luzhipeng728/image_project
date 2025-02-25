import React, { useState } from 'react';
import { Form, Input, Button, Card, message, Tabs } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import api, { BACKEND_URL } from '../utils/api';

const { TabPane } = Tabs;

interface LoginForm {
  username: string;
  password: string;
}

interface RegisterForm extends LoginForm {
  confirmPassword: string;
}

const Login: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const onLogin = async (values: LoginForm) => {
    try {
      setLoading(true);
      console.log('Attempting login with:', values);
      
      // 使用 URLSearchParams 创建 form-urlencoded 格式的数据
      const formData = new URLSearchParams();
      formData.append('username', values.username);
      formData.append('password', values.password);
      console.log(`${BACKEND_URL}/api/auth/login`);
      // 直接使用 axios 发送登录请求，因为需要特殊的 content-type
      const response = await axios.post(`${BACKEND_URL}/api/auth/login`, formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        }
      });
      
      console.log('Login response:', response.data);
      
      if (response.data.access_token) {
        localStorage.setItem('token', `Bearer ${response.data.access_token}`);
        message.success('登录成功');
        console.log('Navigating to dashboard...');
        navigate('/dashboard', { replace: true });
      } else {
        message.error('登录失败：未收到有效的token');
      }
    } catch (error) {
      console.error('Login error:', error);
      message.error('登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  const onRegister = async (values: RegisterForm) => {
    if (values.password !== values.confirmPassword) {
      message.error('两次输入的密码不一致');
      return;
    }

    try {
      setLoading(true);
      await api.post('/api/auth/register', {
        username: values.username,
        password: values.password,
      });
      message.success('注册成功，请登录');
    } catch (error) {
      console.error('Register error:', error);
      message.error('注册失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center', 
      height: '100vh',
      background: '#f0f2f5' 
    }}>
      <Card style={{ width: 400 }}>
        <Tabs defaultActiveKey="login">
          <TabPane tab="登录" key="login">
            <Form onFinish={onLogin}>
              <Form.Item
                name="username"
                rules={[{ required: true, message: '请输入用户名' }]}
              >
                <Input 
                  prefix={<UserOutlined />} 
                  placeholder="用户名" 
                />
              </Form.Item>
              <Form.Item
                name="password"
                rules={[{ required: true, message: '请输入密码' }]}
              >
                <Input.Password 
                  prefix={<LockOutlined />} 
                  placeholder="密码" 
                />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} block>
                  登录
                </Button>
              </Form.Item>
            </Form>
          </TabPane>
          <TabPane tab="注册" key="register">
            <Form onFinish={onRegister}>
              <Form.Item
                name="username"
                rules={[{ required: true, message: '请输入用户名' }]}
              >
                <Input 
                  prefix={<UserOutlined />} 
                  placeholder="用户名" 
                />
              </Form.Item>
              <Form.Item
                name="password"
                rules={[{ required: true, message: '请输入密码' }]}
              >
                <Input.Password 
                  prefix={<LockOutlined />} 
                  placeholder="密码" 
                />
              </Form.Item>
              <Form.Item
                name="confirmPassword"
                rules={[{ required: true, message: '请确认密码' }]}
              >
                <Input.Password 
                  prefix={<LockOutlined />} 
                  placeholder="确认密码" 
                />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} block>
                  注册
                </Button>
              </Form.Item>
            </Form>
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default Login; 