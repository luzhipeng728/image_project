import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Pagination,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Stack,
  Chip,
  CardMedia,
  IconButton,
  Dialog,
  DialogContent,
} from '@mui/material';
import { format } from 'date-fns';
import { ZoomIn } from '@mui/icons-material';
import api from '../utils/api';

interface HistoryRecord {
  id: number;
  generation_type: 'text_to_image' | 'image_to_image';
  prompt: string;
  enhanced_prompt: string;
  source_image_path: string | null;
  result_image_path: string;
  model_name: string;
  model_alias: string;
  created_at: string;
  status: string;
  width: number;
  height: number;
  seed: number;
  enhance: boolean;
}

interface HistoryResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  records: HistoryRecord[];
}

const History: React.FC = () => {
  const [history, setHistory] = useState<HistoryResponse>({
    total: 0,
    page: 1,
    page_size: 12,
    total_pages: 0,
    records: []
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const [generationType, setGenerationType] = useState<string>('all');
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  const fetchHistory = async () => {
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
        ...(generationType !== 'all' && { generation_type: generationType }),
      });

      const response = await api.get(`/api/generation/history?${params}`);
      console.log('API Response:', response.data);
      if (response.data && Array.isArray(response.data.records)) {
        console.log('Records:', response.data.records);
        setHistory(response.data);
      } else {
        console.error('返回的数据格式不正确:', response.data);
        setHistory({
          total: 0,
          page: 1,
          page_size: pageSize,
          total_pages: 0,
          records: []
        });
      }
    } catch (error) {
      console.error('获取历史记录失败:', error);
      setHistory({
        total: 0,
        page: 1,
        page_size: pageSize,
        total_pages: 0,
        records: []
      });
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [page, pageSize, generationType]);

  const handlePageChange = (event: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
  };

  const handleTypeChange = (event: any) => {
    setGenerationType(event.target.value);
    setPage(1); // 重置页码
  };

  const handleImageClick = (imagePath: string) => {
    setSelectedImage(imagePath);
  };

  const handleCloseDialog = () => {
    setSelectedImage(null);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <Typography variant="h5" component="h2">
          生成历史
        </Typography>
        <FormControl sx={{ minWidth: 200 }}>
          <InputLabel>生成类型</InputLabel>
          <Select
            value={generationType}
            label="生成类型"
            onChange={handleTypeChange}
          >
            <MenuItem value="all">全部</MenuItem>
            <MenuItem value="text_to_image">文生图</MenuItem>
            <MenuItem value="image_to_image">图生图</MenuItem>
          </Select>
        </FormControl>
      </Box>

      <Grid container spacing={2}>
        {history?.records.map((record) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={record.id}>
            <Card>
              <Box sx={{ position: 'relative' }}>
                <CardMedia
                  component="img"
                  height="200"
                  image={record.result_image_path}
                  alt={record.prompt}
                  sx={{ objectFit: 'cover', cursor: 'pointer' }}
                  onClick={() => handleImageClick(record.result_image_path)}
                />
                <IconButton
                  sx={{
                    position: 'absolute',
                    right: 8,
                    top: 8,
                    backgroundColor: 'rgba(255, 255, 255, 0.8)',
                    '&:hover': {
                      backgroundColor: 'rgba(255, 255, 255, 0.9)',
                    },
                  }}
                  onClick={() => handleImageClick(record.result_image_path)}
                >
                  <ZoomIn />
                </IconButton>
                {record.generation_type === 'image_to_image' && record.source_image_path && (
                  <Box
                    sx={{
                      position: 'absolute',
                      bottom: -30,
                      right: 8,
                      width: 80,
                      height: 80,
                      border: '2px solid white',
                      borderRadius: '4px',
                      overflow: 'hidden',
                      cursor: 'pointer',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                    }}
                    onClick={() => handleImageClick(record.source_image_path!)}
                  >
                    <CardMedia
                      component="img"
                      height="80"
                      image={record.source_image_path}
                      alt="Source Image"
                      sx={{ objectFit: 'cover' }}
                    />
                  </Box>
                )}
              </Box>
              <CardContent>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <Typography variant="body2" color="text.secondary" noWrap title={record.prompt}>
                    {record.prompt}
                  </Typography>
                  {record.enhanced_prompt && (
                    <Typography variant="caption" color="text.secondary" noWrap title={record.enhanced_prompt}>
                      优化提示词: {record.enhanced_prompt}
                    </Typography>
                  )}
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1 }}>
                    <Chip
                      label={record.generation_type === 'text_to_image' ? '文生图' : '图生图'}
                      size="small"
                      color={record.generation_type === 'text_to_image' ? 'primary' : 'secondary'}
                    />
                    <Chip label={record.model_alias} size="small" variant="outlined" />
                    <Chip 
                      label={`${record.width}x${record.height}`} 
                      size="small" 
                      variant="outlined"
                      color="info"
                    />
                  </Box>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    <Chip 
                      label={`种子: ${record.seed || '默认'}`} 
                      size="small" 
                      variant="outlined"
                    />
                    <Chip 
                      label={`优化: ${record.enhance ? '是' : '否'}`} 
                      size="small" 
                      variant="outlined"
                      color={record.enhance ? 'success' : 'default'}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    {format(new Date(record.created_at), 'yyyy-MM-dd HH:mm:ss')}
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Box sx={{ mt: 3, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2" color="text.secondary">
            每页显示:
          </Typography>
          <Select
            value={pageSize}
            onChange={(e) => {
              const newPageSize = e.target.value as number;
              setPageSize(newPageSize);
              setPage(1); // 重置到第一页
            }}
            size="small"
            sx={{ minWidth: 80 }}
          >
            <MenuItem value={12}>12</MenuItem>
            <MenuItem value={24}>24</MenuItem>
            <MenuItem value={36}>36</MenuItem>
            <MenuItem value={48}>48</MenuItem>
          </Select>
        </Box>

        <Pagination
          count={history.total_pages}
          page={page}
          onChange={handlePageChange}
          color="primary"
          showFirstButton
          showLastButton
          siblingCount={1}
          boundaryCount={1}
        />

        <Typography variant="body2" color="text.secondary">
          共 {history.total} 条记录，第 {history.page} / {history.total_pages} 页
        </Typography>
      </Box>

      <Dialog
        open={!!selectedImage}
        onClose={handleCloseDialog}
        maxWidth="lg"
        fullWidth
      >
        <DialogContent sx={{ p: 0, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          {selectedImage && (
            <img
              src={selectedImage}
              alt="预览图片"
              style={{ maxWidth: '100%', maxHeight: '90vh', objectFit: 'contain' }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
};

export default History; 