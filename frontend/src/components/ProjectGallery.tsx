import React, { useState, useEffect, useRef } from "react";
import {
  Card,
  Select,
  Row,
  Col,
  Button,
  Modal,
  Spin,
  Empty,
  Typography,
  Divider,
  Pagination,
  Checkbox,
  message,
  Form,
  Input,
  Alert,
  Slider,
  Progress,
  List,
  Collapse,
  Statistic,
} from "antd";
import {
  EyeOutlined,
  RightOutlined,
  PictureOutlined,
  DeleteOutlined,
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import api from "../utils/api";

const { Option } = Select;
const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;
const { Panel } = Collapse;

interface Project {
  id: number;
  name: string;
  description: string;
}

interface Model {
  id: number;
  name: string;
  alias: string;
  current_price: number;
}

interface Image {
  id: number;
  file_path: string;
  file_size: number;
  file_type: string;
  width: number;
  height: number;
  project_id: number;
  created_at: string;
  selected?: boolean;
  isGenerating?: boolean;
}

interface GeneratedImage {
  id: number;
  prompt: string;
  model_name: string;
  result_image_path: string;
  source_image_path: string;
  created_at: string;
  seed?: number;
}

// 队列相关类型定义
interface QueueTask {
  image_id: number;
  source_image_path: string;
  results?: GeneratedImage[];
  error?: string;
}

interface QueueStatus {
  queue_id: string;
  status: "waiting" | "processing" | "completed" | "failed";
  total_tasks: number;
  total_completed: number;
  total_failed: number;
  completed_tasks: QueueTask[];
  failed_tasks: QueueTask[];
  error?: string;
  concurrency?: number;
}

// 模拟数据，用于在API不可用时展示
const mockProjects: Project[] = [
  { id: 1, name: "示例项目1", description: "这是一个示例项目" },
  { id: 2, name: "示例项目2", description: "这是另一个示例项目" },
];

const mockImages: Image[] = [
  {
    id: 1,
    file_path: "uploads/projects/1/10,001 Nights Megaways.png",
    file_size: 12345,
    file_type: "image/png",
    width: 800,
    height: 600,
    project_id: 1,
    created_at: new Date().toISOString(),
  },
];

const mockGeneratedImages: GeneratedImage[] = [
  {
    id: 1,
    prompt:
      "背景必须是纯色, 暗色调, 扁平动漫风A mysterious woman in an elaborate costume",
    model_name: "Stable Diffusion",
    result_image_path: "uploads/projects/1/version1.png",
    source_image_path: "uploads/projects/1/10,001 Nights Megaways.png",
    created_at: new Date().toISOString(),
  },
  {
    id: 2,
    prompt:
      "背景必须是纯色, 暗色调, 扁平动漫风A mysterious woman in an elaborate costume",
    model_name: "Stable Diffusion",
    result_image_path: "uploads/projects/1/version2.png",
    source_image_path: "uploads/projects/1/10,001 Nights Megaways.png",
    created_at: new Date().toISOString(),
  },
  {
    id: 3,
    prompt:
      "背景必须是纯色, 暗色调, 扁平动漫风A mysterious woman in an elaborate costume",
    model_name: "Stable Diffusion",
    result_image_path: "uploads/projects/1/version3.png",
    source_image_path: "uploads/projects/1/10,001 Nights Megaways.png",
    created_at: new Date().toISOString(),
  },
  {
    id: 4,
    prompt:
      "背景必须是纯色, 暗色调, 扁平动漫风A mysterious woman in an elaborate costume",
    model_name: "Stable Diffusion",
    result_image_path: "uploads/projects/1/version4.png",
    source_image_path: "uploads/projects/1/10,001 Nights Megaways.png",
    created_at: new Date().toISOString(),
  },
];

const ProjectGallery: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<number | null>(null);
  const [images, setImages] = useState<Image[]>([]);
  const [generatedImages, setGeneratedImages] = useState<{
    [key: string]: GeneratedImage[];
  }>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [currentImagePath, setCurrentImagePath] = useState<string>("");
  const [currentGeneratedImages, setCurrentGeneratedImages] = useState<
    GeneratedImage[]
  >([]);
  const [useMockData, setUseMockData] = useState<boolean>(false);
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState<number | null>(null);
  const [pageSize, setPageSize] = useState<number>(20);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalImages, setTotalImages] = useState<number>(0);
  const [selectedImages, setSelectedImages] = useState<number[]>([]);
  const [generating, setGenerating] = useState<boolean>(false);

  // 添加默认提示词状态
  const [defaultPrompt, setDefaultPrompt] = useState<string>(
    "参考以上图片，保留图片中的整体风格，生成一张优化后的图片，生成的图片描述必须是英文，图片中的存在文字，不需要描述，只需要描述图片中画面信息"
  );
  // 添加图片提示词映射
  const [imagePrompts, setImagePrompts] = useState<Record<number, string>>({});
  // 添加编辑提示词模态框状态
  const [promptModalVisible, setPromptModalVisible] = useState<boolean>(false);
  const [currentEditingImage, setCurrentEditingImage] = useState<Image | null>(
    null
  );
  const [promptForm] = Form.useForm();
  // 添加调整生成图片的模态框状态
  const [
    adjustGeneratedImageModalVisible,
    setAdjustGeneratedImageModalVisible,
  ] = useState<boolean>(false);
  const [currentEditingGeneratedImage, setCurrentEditingGeneratedImage] =
    useState<GeneratedImage | null>(null);
  const [adjustGeneratedImageForm] = Form.useForm();
  const [viewMode, setViewMode] = useState<"original" | "generated">(
    "original"
  );
  const [selectedImage, setSelectedImage] = useState<Image | null>(null);
  const [previewVisible, setPreviewVisible] = useState<boolean>(false);
  const [previewImage, setPreviewImage] = useState<string>("");
  const [previewTitle, setPreviewTitle] = useState<string>("");
  const [isSelectionMode, setIsSelectionMode] = useState<boolean>(false);
  const [batchGenerationVisible, setBatchGenerationVisible] =
    useState<boolean>(false);
  const [batchPrompt, setBatchPrompt] = useState<string>("");
  const [generatingBatch, setGeneratingBatch] = useState<boolean>(false);
  const [generationResults, setGenerationResults] = useState<any[]>([]);
  const [showGenerationResults, setShowGenerationResults] =
    useState<boolean>(false);
  const [currentImageGenerations, setCurrentImageGenerations] = useState<
    GeneratedImage[]
  >([]);
  const [viewingGenerationsFor, setViewingGenerationsFor] = useState<
    string | null
  >(null);
  const [generatingSingle, setGeneratingSingle] = useState<boolean>(false);
  const [form] = Form.useForm();

  // 添加新的状态变量
  const [queueSettingsModalVisible, setQueueSettingsModalVisible] =
    useState<boolean>(false);
  const [concurrency, setConcurrency] = useState<number>(5); // 默认并发数为5
  const [queueId, setQueueId] = useState<string | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const queueStatusInterval = useRef<NodeJS.Timeout | null>(null);

  // 添加一个状态来跟踪是否已经检查了活跃队列
  const [checkedActiveQueues, setCheckedActiveQueues] =
    useState<boolean>(false);
  // 添加一个状态来控制队列状态区域的显示/隐藏
  const [showQueueStatus, setShowQueueStatus] = useState<boolean>(false);

  // 获取项目列表
  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const response = await api.get("/api/projects/");
        if (response.data && response.data.length > 0) {
          setProjects(response.data);
          setSelectedProject(response.data[0].id);
        } else {
          // 如果没有真实数据，使用模拟数据
          setUseMockData(true);
          setProjects(mockProjects);
          setSelectedProject(mockProjects[0].id);
        }
      } catch (error) {
        console.error("获取项目列表失败:", error);
        // API调用失败时使用模拟数据
        setUseMockData(true);
        setProjects(mockProjects);
        setSelectedProject(mockProjects[0].id);
      }
    };

    fetchProjects();
    fetchModels();
  }, []);

  // 获取模型列表
  const fetchModels = async () => {
    try {
      const response = await api.get("/api/generation/models");
      if (response.data && response.data.length > 0) {
        setModels(response.data);
        setSelectedModel(response.data[0].id);
      }
    } catch (error) {
      console.error("获取模型列表失败:", error);
      // 使用模拟数据
      const mockModels = [
        { id: 1, name: "model1", alias: "Stable Diffusion", current_price: 0 },
        { id: 2, name: "model2", alias: "DALL-E", current_price: 0 },
      ];
      setModels(mockModels);
      setSelectedModel(mockModels[0].id);
    }
  };

  // 获取项目图片
  useEffect(() => {
    if (selectedProject) {
      if (useMockData) {
        // 使用模拟数据
        const filteredImages = mockImages.filter(
          (img) => img.project_id === selectedProject
        );
        setImages(filteredImages);
        setTotalImages(filteredImages.length);
        const mockGeneratedImagesMap: Record<string, GeneratedImage[]> = {};
        mockImages.forEach((image) => {
          mockGeneratedImagesMap[image.file_path] = mockGeneratedImages;
        });
        setGeneratedImages(mockGeneratedImagesMap);
      } else {
        // 使用真实API数据
        fetchProjectImages(selectedProject);
      }

      // 如果还没有检查活跃队列，则进行检查
      if (!checkedActiveQueues) {
        checkActiveQueues();
      }
    }
  }, [
    selectedProject,
    useMockData,
    currentPage,
    pageSize,
    checkedActiveQueues,
  ]);

  const fetchProjectImages = async (projectId: number) => {
    setLoading(true);
    try {
      // 先获取总数
      const countResponse = await api.get(
        `/api/projects/${projectId}/images/count`
      );
      const totalCount = countResponse.data.total || 0;
      setTotalImages(totalCount);

      // 获取分页数据
      const response = await api.get(`/api/projects/${projectId}/images`, {
        params: {
          skip: (currentPage - 1) * pageSize,
          limit: pageSize,
        },
      });

      // 添加selected属性
      const imagesWithSelection = response.data.map((img: Image) => ({
        ...img,
        selected: false,
      }));

      setImages(imagesWithSelection);

      // 获取每张图片的生成结果
      const generatedImagesMap: Record<string, GeneratedImage[]> = {};
      for (const image of imagesWithSelection) {
        try {
          // 这里假设有一个API可以获取基于原始图片的生成结果
          // 实际实现可能需要根据后端API调整
          const genResponse = await api.get(
            `/api/generation/results?source_image=${image.file_path}`
          );
          generatedImagesMap[image.file_path] = genResponse.data || [];
        } catch (error) {
          console.error(`获取图片${image.id}的生成结果失败:`, error);
          generatedImagesMap[image.file_path] = [];
        }
      }
      setGeneratedImages(generatedImagesMap);
    } catch (error) {
      console.error("获取项目图片失败:", error);
      // 如果API调用失败，使用模拟数据
      setUseMockData(true);
    } finally {
      setLoading(false);
    }
  };

  const handleProjectChange = (value: number) => {
    setSelectedProject(value);
    setCurrentPage(1);
    setSelectedImages([]);
  };

  const handleModelChange = (value: number) => {
    setSelectedModel(value);
  };

  const handlePageChange = (page: number, pageSize?: number) => {
    setCurrentPage(page);
    if (pageSize) {
      setPageSize(pageSize);
    }
    setSelectedImages([]);

    // 确保在页面变化时重新获取数据
    if (selectedProject && !useMockData) {
      fetchProjectImages(selectedProject);
    }
  };

  const handlePageSizeChange = (current: number, size: number) => {
    setPageSize(size);
    setCurrentPage(1);
    setSelectedImages([]);

    // 确保在页面大小变化时重新获取数据
    if (selectedProject && !useMockData) {
      fetchProjectImages(selectedProject);
    }
  };

  const showAllGeneratedImages = (
    imagePath: string,
    images: GeneratedImage[]
  ) => {
    setCurrentImagePath(imagePath);
    // 按照创建时间倒序排序
    if (images && images.length > 0) {
      const sortedImages = [...images].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setCurrentGeneratedImages(sortedImages);
    } else {
      setCurrentGeneratedImages([]);
    }
    setModalVisible(true);
  };

  // 处理图片选择
  const handleImageSelect = (imageId: number) => {
    setImages((prevImages) =>
      prevImages.map((img) =>
        img.id === imageId ? { ...img, selected: !img.selected } : img
      )
    );

    setSelectedImages((prevSelected) => {
      if (prevSelected.includes(imageId)) {
        return prevSelected.filter((id) => id !== imageId);
      } else {
        return [...prevSelected, imageId];
      }
    });
  };

  // 全选/取消全选
  const handleSelectAll = (checked: boolean) => {
    setImages((prevImages) =>
      prevImages.map((img) => ({ ...img, selected: checked }))
    );

    if (checked) {
      setSelectedImages(images.map((img) => img.id));
    } else {
      setSelectedImages([]);
    }
  };

  // 保存生成结果到数据库
  const saveGenerationResults = async (
    sourceImagePath: string,
    generatedImages: any[]
  ) => {
    try {
      await api.post("/api/generation/save-results", {
        source_image_path: sourceImagePath,
        generated_images: generatedImages,
        project_id: selectedProject,
      });

      // 仅更新生成图片列表
      setGeneratedImages((prev) => ({
        ...prev,
        [sourceImagePath]: [
          ...generatedImages.map((img) => ({
            id: img.id || Math.random(),
            prompt: img.prompt,
            model_name: img.model_name,
            result_image_path: img.result_image_path,
            source_image_path: sourceImagePath,
            created_at: img.created_at || new Date().toISOString(),
            seed: img.seed,
          })),
          ...(prev[sourceImagePath] || []), // 保留已有生成结果
        ],
      }));

      message.success("生成结果已保存");
    } catch (error) {
      console.error("保存生成结果失败:", error);
      message.error("保存生成结果失败");
    }
  };

  // 处理单张图片生成
  const handleGenerateImage = async (image: Image) => {
    if (!selectedModel) {
      message.error("请先选择一个模型");
      return;
    }

    // 直接使用图片的提示词，不再弹出模态框
    setSelectedImage(image);

    // 获取当前图片的提示词
    const currentPrompt = imagePrompts[image.id] || defaultPrompt;

    // 开始生成过程
    setGeneratingSingle(true);

    try {
      // 生成三个不同的种子值
      const seeds = Array(3)
        .fill(0)
        .map(() => Math.floor(Math.random() * 2147483647));

      // 更新图片状态为生成中
      setImages((prevImages) =>
        prevImages.map((img) =>
          img.id === image.id ? { ...img, isGenerating: true } : img
        )
      );

      // 准备图片URL
      const imageUrl = image.file_path && image.file_path.startsWith("http")
        ? image.file_path
        : `${api.defaults.baseURL}/${image.file_path || ""}`;

      console.log("生成图片，使用URL:", imageUrl);
      console.log("使用提示词:", currentPrompt);

      message.loading("正在生成3个不同随机种子的图片变体，请稍候...", 0);

      // 并行发送三个请求
      const generationPromises = seeds.map((seed) =>
        api.post("/api/generation/image-to-image", {
          image_url: imageUrl,
          prompt: currentPrompt,
          model_id: selectedModel,
          seed: seed,
          project_id: selectedProject,
        })
      );

      const responses = await Promise.all(generationPromises);

      // 处理生成结果
      const newGeneratedImages = responses.map((response, index) => {
        // 获取优化后的提示词 (只用于生成结果记录，不更新到状态)
        const optimizedPrompt = response.data.prompt || currentPrompt;

        return {
          id: response.data.id,
          prompt: optimizedPrompt, // 使用API返回的优化提示词
          model_name:
            models.find((m) => m.id === selectedModel)?.alias || "unknown",
          result_image_path: response.data.image_url,
          source_image_path: image.file_path,
          created_at: new Date().toISOString(),
          seed: seeds[index],
        };
      });

      console.log("生成的图片:", newGeneratedImages);

      // 保存生成结果
      await saveGenerationResults(image.file_path, newGeneratedImages);

      // 更新状态
      setImages((prevImages) =>
        prevImages.map((img) =>
          img.id === image.id ? { ...img, isGenerating: false } : img
        )
      );

      // 显示生成结果
      // 按照创建时间倒序排序
      const sortedImages = [...newGeneratedImages].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setCurrentImageGenerations(sortedImages);
      setViewingGenerationsFor(image.file_path);

      message.destroy();
      message.success("图片生成成功");
    } catch (error) {
      console.error("生成图片失败:", error);
      message.destroy();
      message.error("生成图片失败");

      // 更新状态
      setImages((prevImages) =>
        prevImages.map((img) =>
          img.id === image.id ? { ...img, isGenerating: false } : img
        )
      );
    } finally {
      setGeneratingSingle(false);
    }
  };

  // 批量生成图片
  const handleBatchGenerate = async () => {
    if (selectedImages.length === 0) {
      message.warning("请先选择要生成的图片");
      return;
    }

    if (!selectedModel) {
      message.error("请先选择模型");
      return;
    }

    // 打开并发设置模态框
    setQueueSettingsModalVisible(true);
  };

  // 检查用户的活跃队列
  const checkActiveQueues = async () => {
    try {
      const response = await api.get("/api/generation/active-queues");
      const activeQueues = response.data.queues;

      if (activeQueues && activeQueues.length > 0) {
        // 找到最新的活跃队列
        const latestQueue = activeQueues[0];

        // 如果队列与当前项目相关，则恢复状态
        if (latestQueue.project_id === selectedProject) {
          message.info(`发现正在进行的批量生成任务，正在恢复状态...`);

          // 设置队列ID并开始轮询状态
          setQueueId(latestQueue.queue_id);
          startPollingQueueStatus(latestQueue.queue_id);

          // 显示队列状态区域
          setShowQueueStatus(true);

          // 更新图片生成状态
          if (
            latestQueue.completed_tasks &&
            latestQueue.completed_tasks.length > 0
          ) {
            // 处理已完成的任务
            const updatedGeneratedImages = { ...generatedImages };

            latestQueue.completed_tasks.forEach((task: QueueTask) => {
              if (task.results && task.results.length > 0) {
                const sourcePath = task.source_image_path;

                if (!updatedGeneratedImages[sourcePath]) {
                  updatedGeneratedImages[sourcePath] = [];
                }

                // 添加新的结果
                updatedGeneratedImages[sourcePath] = [
                  ...task.results,
                  ...updatedGeneratedImages[sourcePath],
                ];
              }
            });

            setGeneratedImages(updatedGeneratedImages);
          }

          // 标记正在生成的图片
          const processingImageIds = new Set<number>();

          // 收集所有任务中的图片ID
          if (latestQueue.completed_tasks) {
            latestQueue.completed_tasks.forEach((task: QueueTask) => {
              processingImageIds.add(task.image_id);
            });
          }

          if (latestQueue.failed_tasks) {
            latestQueue.failed_tasks.forEach((task: QueueTask) => {
              processingImageIds.add(task.image_id);
            });
          }

          // 更新图片状态
          setImages((prevImages) =>
            prevImages.map((img) => ({
              ...img,
              isGenerating:
                processingImageIds.has(img.id) &&
                latestQueue.status !== "completed" &&
                latestQueue.status !== "failed",
            }))
          );
        }
      }

      // 标记已检查活跃队列
      setCheckedActiveQueues(true);
    } catch (error) {
      console.error("检查活跃队列失败:", error);
      setCheckedActiveQueues(true);
    }
  };

  // 组件挂载时检查本地存储中的队列状态
  useEffect(() => {
    // 从本地存储中获取队列ID
    const savedQueueId = localStorage.getItem("activeQueueId");
    const savedProjectId = localStorage.getItem("activeQueueProjectId");

    if (
      savedQueueId &&
      savedProjectId &&
      parseInt(savedProjectId) === selectedProject
    ) {
      // 如果有保存的队列ID且与当前项目匹配，则设置队列ID
      setQueueId(savedQueueId);

      // 开始轮询队列状态
      startPollingQueueStatus(savedQueueId);

      // 显示队列状态区域
      setShowQueueStatus(true);
    }

    // 组件卸载时清理
    return () => {
      // 停止轮询
      stopPollingQueueStatus();
    };
  }, []);

  // 修改startPollingQueueStatus方法，保存队列ID到本地存储
  const startPollingQueueStatus = (queueId: string) => {
    // 先停止可能存在的轮询
    stopPollingQueueStatus();

    // 保存队列ID到本地存储
    localStorage.setItem("activeQueueId", queueId);
    if (selectedProject) {
      localStorage.setItem("activeQueueProjectId", selectedProject.toString());
    }

    // 显示队列状态区域
    setShowQueueStatus(true);

    // 开始新的轮询
    queueStatusInterval.current = setInterval(() => {
      fetchQueueStatus(queueId);
    }, 3000); // 每3秒查询一次
  };

  // 修改stopPollingQueueStatus方法，清除本地存储中的队列ID
  const stopPollingQueueStatus = () => {
    if (queueStatusInterval.current) {
      clearInterval(queueStatusInterval.current);
      queueStatusInterval.current = null;
    }

    // 清除本地存储中的队列ID
    localStorage.removeItem("activeQueueId");
    localStorage.removeItem("activeQueueProjectId");

    // 隐藏队列状态区域
    setShowQueueStatus(false);
  };

  // 获取队列状态
  const fetchQueueStatus = async (queueId: string) => {
    try {
      const response = await api.get(`/api/generation/queue-status/${queueId}`);
      const status: QueueStatus = response.data;

      // 更新队列状态，包括并发数
      setQueueStatus(status);

      // 更新生成结果
      if (status.completed_tasks && status.completed_tasks.length > 0) {
        const updatedGeneratedImages = { ...generatedImages };

        // 处理完成的任务结果
        status.completed_tasks.forEach((task: QueueTask) => {
          if (task.results && task.results.length > 0) {
            const sourcePath = task.source_image_path;

            // 更新当前图片的生成结果
            if (!updatedGeneratedImages[sourcePath]) {
              updatedGeneratedImages[sourcePath] = [];
            }

            // 检查是否已经添加过这些结果
            const existingIds = new Set(
              updatedGeneratedImages[sourcePath].map((img) => img.id)
            );

            // 只添加新的结果
            const newResults = task.results.filter(
              (result: GeneratedImage) => !existingIds.has(result.id)
            );

            if (newResults.length > 0) {
              updatedGeneratedImages[sourcePath] = [
                ...newResults,
                ...updatedGeneratedImages[sourcePath],
              ];
            }
          }
        });

        // 更新生成图片的状态
        setGeneratedImages(updatedGeneratedImages);
      }

      // 如果队列已完成或失败，停止轮询并清除本地存储
      if (status.status === "completed" || status.status === "failed") {
        stopPollingQueueStatus();

        // 清除所有图片的生成状态
        setImages((prevImages) =>
          prevImages.map((img) => ({ ...img, isGenerating: false }))
        );

        // 显示完成消息
        if (status.status === "completed") {
          message.success(
            `批量生成队列已完成，成功生成${status.total_completed}张图片`
          );
        } else {
          message.error(`批量生成队列失败，请查看详细信息`);
        }
      }
    } catch (error) {
      console.error("获取队列状态失败:", error);

      // 如果获取状态失败（可能是队列已过期），停止轮询
      stopPollingQueueStatus();
    }
  };

  // 删除单张图片
  const handleDeleteImage = async (imageId: number) => {
    try {
      // 添加确认对话框
      Modal.confirm({
        title: "确认删除",
        content: "删除原始图片将同步删除生成后的图片。是否删除？",
        okText: "确认",
        cancelText: "取消",
        onOk: async () => {
          message.loading("正在删除图片...", 0);
          try {
            // 修改API调用路径
            await api.delete(
              `/api/projects/${selectedProject}/images/${imageId}`
            );
            message.destroy();
            message.success("图片删除成功");

            // 刷新图片列表
            if (selectedProject) {
              fetchProjectImages(selectedProject);
            }
          } catch (error) {
            message.destroy();
            console.error("删除图片失败:", error);
            message.error("删除图片失败");
          }
        },
      });
    } catch (error) {
      console.error("删除图片失败:", error);
      message.error("删除图片失败");
    }
  };

  // 批量删除图片
  const handleBatchDelete = () => {
    if (selectedImages.length === 0) {
      message.warning("请先选择要删除的图片");
      return;
    }

    Modal.confirm({
      title: "确认批量删除",
      content: `您确定要删除选中的 ${selectedImages.length} 张图片吗？删除原始图片将同步删除生成后的图片。`,
      okText: "确认",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        message.loading("正在批量删除图片...", 0);
        try {
          // 使用Promise.all并行处理所有删除请求
          await Promise.all(
            selectedImages.map((imageId) =>
              api.delete(`/api/projects/${selectedProject}/images/${imageId}`)
            )
          );

          message.destroy();
          message.success(`成功删除 ${selectedImages.length} 张图片`);

          // 清空选择的图片
          setSelectedImages([]);

          // 刷新图片列表
          if (selectedProject) {
            fetchProjectImages(selectedProject);
          }
        } catch (error) {
          message.destroy();
          console.error("批量删除图片失败:", error);
          message.error("批量删除图片失败");
        }
      },
    });
  };

  // 在随机Seed按钮的点击处理中，更新当前生成的图片列表
  const handleRegenerate = async (
    genImage: GeneratedImage,
    newGeneratedImage: any
  ) => {
    // 更新主列表
    setGeneratedImages((prev) => {
      const sourcePath = genImage.source_image_path;
      const updatedImages = prev[sourcePath].map((img) =>
        img.id === genImage.id ? newGeneratedImage : img
      );
      return {
        ...prev,
        [sourcePath]: [...updatedImages].sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ),
      };
    });

    // 如果当前在查看所有生成图片的模态框，更新当前显示的列表
    if (modalVisible) {
      setCurrentGeneratedImages((prev) =>
        prev
          .map((img) => (img.id === genImage.id ? newGeneratedImage : img))
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime()
          )
      );
    }

    // 如果当前在单张图片的生成结果区域，更新当前图片的生成列表
    if (viewingGenerationsFor === genImage.source_image_path) {
      setCurrentImageGenerations((prev) =>
        prev
          .map((img) => (img.id === genImage.id ? newGeneratedImage : img))
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime()
          )
      );
    }
  };

  // 取消队列
  const handleCancelQueue = async () => {
    if (!queueId) return;

    try {
      await api.post(`/api/generation/cancel-queue/${queueId}`);
      message.success("已取消批量生成队列");
      stopPollingQueueStatus();
    } catch (error) {
      console.error("取消队列失败:", error);
      message.error("取消队列失败");
    }
  };

  // 提交批量生成队列
  const submitBatchGenerationQueue = async (concurrency: number) => {
    setGenerating(true);

    try {
      const selectedImageObjects = images.filter((img) =>
        selectedImages.includes(img.id)
      );
      message.loading(
        `正在将${selectedImageObjects.length}张图片（每张生成3个随机种子变体，共${selectedImageObjects.length * 3}个任务）添加到生成队列，请稍候...`,
        0
      );

      // 为所有选中的图片设置生成状态
      setImages((prevImages) =>
        prevImages.map((img) =>
          selectedImages.includes(img.id) ? { ...img, isGenerating: true } : img
        )
      );

      // 准备批量生成任务数据
      const tasks = selectedImageObjects.map((image) => {
        // 直接使用图片保存的提示词或默认提示词
        const prompt = imagePrompts[image.id] || defaultPrompt;

        // 计算等比例缩放后的尺寸，确保宽高都小于1024
        let width = image.width;
        let height = image.height;
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
          console.log(
            `图片 ${image.id} 已等比例缩放: ${image.width}x${image.height} -> ${width}x${height}`
          );
        }

        // 构造图片URL
        const imageUrl = image.file_path && image.file_path.startsWith("http")
          ? image.file_path
          : `${api.defaults.baseURL}/uploads/${(image.file_path || "").replace(
              /^uploads\//,
              ""
            )}`;

        // 为每张图片生成3个随机种子值
        const randomSeeds = Array(3).fill(0).map(() => Math.floor(Math.random() * 1000000));

        return {
          image_id: image.id,
          image_url: imageUrl,
          prompt: prompt,
          width: width,
          height: height,
          seeds: randomSeeds, // 使用3个随机种子值
          source_image_path: image.file_path,
        };
      });

      // 调用创建队列的API
      const response = await api.post("/api/generation/create-queue", {
        tasks: tasks,
        model_id: selectedModel,
        project_id: selectedProject,
        concurrency: concurrency,
      });

      message.destroy();

      if (response.data.queue_id) {
        message.success(
          `已成功创建批量生成队列，队列ID: ${response.data.queue_id}，将为${selectedImageObjects.length}张图片生成${selectedImageObjects.length * 3}个变体`
        );

        // 启动轮询队列状态
        setQueueId(response.data.queue_id);
        startPollingQueueStatus(response.data.queue_id);

        // 显示队列状态区域
        setShowQueueStatus(true);
      } else {
        message.error("创建队列失败，请稍后重试");
      }

      // 清空选择
      setSelectedImages([]);
    } catch (error: any) {
      console.error("创建批量生成队列失败:", error);

      // 提取错误信息
      let errorMessage = "创建批量生成队列失败";

      if (error.response?.data?.detail) {
        if (typeof error.response.data.detail === "string") {
          errorMessage = `创建批量生成队列失败: ${error.response.data.detail}`;
        } else if (
          Array.isArray(error.response.data.detail) &&
          error.response.data.detail.length > 0
        ) {
          errorMessage = `创建批量生成队列失败: ${
            error.response.data.detail[0].msg || "未知错误"
          }`;
        }
      }

      message.error(errorMessage);

      // 清除所有图片的生成状态
      setImages((prevImages) =>
        prevImages.map((img) =>
          selectedImages.includes(img.id)
            ? { ...img, isGenerating: false }
            : img
        )
      );
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div style={{ padding: "20px" }}>
      {/* 添加队列状态区域到顶部 */}
      {showQueueStatus && queueStatus && (
        <Card
          style={{
            marginBottom: 20,
            boxShadow: "0 2px 8px rgba(0,0,0,0.09)",
            borderRadius: "8px",
            background:
              queueStatus.status === "processing"
                ? "#f6ffed"
                : queueStatus.status === "completed"
                ? "#f6ffed"
                : queueStatus.status === "failed"
                ? "#fff2f0"
                : "#e6f7ff",
          }}
          title={
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span style={{ fontWeight: "bold", fontSize: "16px" }}>
                批量生成任务状态
                {queueStatus.status === "processing" && (
                  <Spin size="small" style={{ marginLeft: 10 }} />
                )}
              </span>
              <Button
                icon={<CloseOutlined />}
                type="text"
                size="small"
                onClick={() => {
                  if (
                    queueStatus.status === "processing" ||
                    queueStatus.status === "waiting"
                  ) {
                    Modal.confirm({
                      title: "确认关闭",
                      content:
                        "任务正在进行中，关闭状态面板不会停止任务。您确定要关闭吗？",
                      okText: "关闭面板",
                      cancelText: "取消",
                      onOk: () => setShowQueueStatus(false),
                    });
                  } else {
                    setShowQueueStatus(false);
                  }
                }}
              />
            </div>
          }
        >
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Progress
                percent={
                  queueStatus.total_tasks
                    ? Math.round(
                        (queueStatus.completed_tasks as any /
                          queueStatus.total_tasks) *
                          100
                      )
                    : 0
                }
                status={
                  queueStatus.status === "completed"
                    ? "success"
                    : queueStatus.status === "failed"
                    ? "exception"
                    : "active"
                }
                strokeWidth={10}
                format={(percent) =>
                  `${percent}% (${queueStatus.completed_tasks}/${queueStatus.total_tasks})`
                }
              />
            </Col>

            <Col span={6}>
              <Statistic
                title={<span style={{ fontSize: "14px" }}>状态</span>}
                value={
                  queueStatus.status === "processing"
                    ? "处理中"
                    : queueStatus.status === "completed"
                    ? "已完成"
                    : queueStatus.status === "failed"
                    ? "失败"
                    : "等待中"
                }
                valueStyle={{
                  color:
                    queueStatus.status === "processing"
                      ? "#1890ff"
                      : queueStatus.status === "completed"
                      ? "#52c41a"
                      : queueStatus.status === "failed"
                      ? "#f5222d"
                      : "#faad14",
                  fontSize: "16px",
                }}
              />
            </Col>
            <Col span={6}>
              <Statistic
                title={<span style={{ fontSize: "14px" }}>总任务数</span>}
                value={queueStatus.total_tasks || 0}
                valueStyle={{ fontSize: "16px" }}
              />
            </Col>
            <Col span={6}>
              <Statistic
                title={<span style={{ fontSize: "14px" }}>已完成</span>}
                value={queueStatus.completed_tasks as any || 0}
                valueStyle={{ color: "#52c41a", fontSize: "16px" }}
              />
            </Col>
            <Col span={6}>
              <Statistic
                title={<span style={{ fontSize: "14px" }}>失败任务</span>}
                value={queueStatus.total_failed || 0}
                valueStyle={{
                  color:
                    queueStatus.total_failed > 0
                      ? "#f5222d"
                      : "rgba(0, 0, 0, 0.45)",
                  fontSize: "16px",
                }}
              />
            </Col>

            <Col span={24}>
              <Alert
                type="info"
                message="生成详情"
                description={
                  <div>
                    <p>每张原始图片将生成3个不同随机种子的变体，总计 {Math.round(queueStatus.total_tasks / 3)} 张原始图片，{queueStatus.total_tasks} 个生成任务。</p>
                    <p>当前并发数: {queueStatus.concurrency || concurrency}，预计剩余时间: 约 {Math.ceil((queueStatus.total_tasks - queueStatus.total_completed) / (queueStatus.concurrency || concurrency) * 5)} 分钟</p>
                  </div>
                }
                style={{ marginBottom: 16, marginTop: 8 }}
              />
            </Col>

            {queueStatus.status === "failed" && queueStatus.error && (
              <Col span={24}>
                <Alert
                  message="错误信息"
                  description={queueStatus.error}
                  type="error"
                  showIcon
                />
              </Col>
            )}

            {queueStatus.failed_tasks &&
              queueStatus.failed_tasks.length > 0 && (
                <Col span={24}>
                  <Collapse bordered={false} ghost>
                    <Panel
                      header={
                        <Text type="danger">
                          查看失败任务详情 ({queueStatus.failed_tasks.length})
                        </Text>
                      }
                      key="1"
                    >
                      <List
                        dataSource={queueStatus.failed_tasks}
                        renderItem={(task: QueueTask) => (
                          <List.Item>
                            <List.Item.Meta
                              title={`图片ID: ${task.image_id}`}
                              description={task.error || "未知错误"}
                            />
                          </List.Item>
                        )}
                      />
                    </Panel>
                  </Collapse>
                </Col>
              )}

            {(queueStatus.status === "processing" ||
              queueStatus.status === "waiting") && (
              <Col span={24} style={{ textAlign: "right" }}>
                <Button danger onClick={handleCancelQueue}>
                  取消任务
                </Button>
              </Col>
            )}
          </Row>
        </Card>
      )}

      <div style={{ marginBottom: 20 }}>
        <Title level={2}>项目图库</Title>
        <Paragraph>选择项目查看上传的图片及其生成结果</Paragraph>

        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={6}>
            <div style={{ marginBottom: 10 }}>
              <Text strong>选择项目：</Text>
            </div>
            <Select
              placeholder="选择项目"
              style={{ width: "100%" }}
              onChange={handleProjectChange}
              value={selectedProject}
            >
              {projects.map((project) => (
                <Option key={project.id} value={project.id}>
                  {project.name}
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={6}>
            <div style={{ marginBottom: 10 }}>
              <Text strong>选择模型：</Text>
            </div>
            <Select
              placeholder="选择模型"
              style={{ width: "100%" }}
              onChange={handleModelChange}
              value={selectedModel}
            >
              {models.map((model) => (
                <Option key={model.id} value={model.id}>
                  {model.alias}
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 10 }}>
              <Text strong>批量操作：</Text>
            </div>
            <Button
              danger
              icon={<DeleteOutlined />}
              onClick={handleBatchDelete}
              disabled={selectedImages.length === 0}
              style={{ marginRight: 8 }}
            >
              批量删除 ({selectedImages.length})
            </Button>
            {queueId && !showQueueStatus && (
              <Button
                type="default"
                icon={<ReloadOutlined />}
                onClick={() => setShowQueueStatus(true)}
              >
                显示任务状态
              </Button>
            )}
          </Col>
        </Row>
        <Row style={{ marginBottom: 20 }}>
          <Col span={24}>
            <Checkbox
              onChange={(e) => handleSelectAll(e.target.checked)}
              checked={
                selectedImages.length > 0 &&
                selectedImages.length === images.length
              }
              indeterminate={
                selectedImages.length > 0 &&
                selectedImages.length < images.length
              }
            >
              全选
            </Checkbox>
          </Col>
        </Row>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "50px" }}>
          <Spin size="large" />
        </div>
      ) : images.length === 0 ? (
        <Empty description="该项目下暂无图片" />
      ) : (
        <div>
          {images.map((image) => (
            <Card key={image.id} style={{ marginBottom: 30, padding: "20px" }}>
              <Row style={{ marginBottom: 16 }}>
                <Col span={24}>
                  <Checkbox
                    checked={image.selected}
                    onChange={() => handleImageSelect(image.id)}
                  >
                    <Text strong>{image.file_path.split("/").pop()}</Text>
                  </Checkbox>
                </Col>
              </Row>
              <Row gutter={24}>
                <Col span={8}>
                  <div style={{ textAlign: "center" }}>
                    <div
                      style={{
                        border: "1px solid #e0e0e0",
                        borderRadius: "8px",
                        padding: "12px",
                        backgroundColor: "#f9f9f9",
                        position: "relative",
                      }}
                    >
                      <div
                        style={{
                          position: "absolute",
                          top: 0,
                          right: 0,
                          backgroundColor: "rgba(0, 0, 0, 0.6)",
                          color: "white",
                          padding: "4px 8px",
                          borderTopRightRadius: "8px",
                          borderBottomLeftRadius: "8px",
                          fontSize: "12px",
                          fontWeight: "bold",
                          zIndex: 1,
                        }}
                      >
                        原始图片
                      </div>
                      <img
                        src={
                          useMockData
                            ? `/example-image.jpg`
                            : image.file_path && image.file_path.startsWith("http")
                            ? image.file_path
                            : `${
                                api.defaults.baseURL
                              }/uploads/${(image.file_path || "").replace(
                                /^uploads\//,
                                ""
                              )}`
                        }
                        alt="原始图片"
                        style={{
                          maxWidth: "100%",
                          maxHeight: 400,
                          objectFit: "contain",
                          cursor: "pointer",
                        }}
                        onClick={() => {
                          const imgUrl = useMockData
                            ? `/example-image.jpg`
                            : image.file_path && image.file_path.startsWith("http")
                            ? image.file_path
                            : `${
                                api.defaults.baseURL
                              }/uploads/${(image.file_path || "").replace(
                                /^uploads\//,
                                ""
                              )}`;
                          setPreviewImage(imgUrl);
                          setPreviewTitle(
                            (image.file_path || "").split("/").pop() || "原始图片"
                          );
                          setPreviewVisible(true);
                        }}
                      />
                      <div
                        style={{
                          marginTop: 10,
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Button
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => handleDeleteImage(image.id)}
                        >
                          删除
                        </Button>
                        <Button
                          type="primary"
                          icon={<PictureOutlined />}
                          onClick={() => handleGenerateImage(image)}
                          loading={image.isGenerating}
                          disabled={image.isGenerating}
                        >
                          {image.isGenerating ? "生成中..." : "生成图片"}
                        </Button>
                      </div>
                    </div>
                  </div>
                </Col>
                <Col span={16}>
                  <div>
                    <div style={{ marginBottom: 20 }}>
                      <Card
                        bordered={false}
                        style={{ background: "#f5f5f5", cursor: "pointer" }}
                        onClick={() => {
                          setCurrentEditingImage(image);
                          promptForm.setFieldsValue({
                            prompt: imagePrompts[image.id] || defaultPrompt,
                          });
                          setPromptModalVisible(true);
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <Text>{imagePrompts[image.id] || defaultPrompt}</Text>
                        </div>
                      </Card>
                    </div>

                    <div>
                      <Row>
                        <Col span={24}>
                          <div
                            style={{
                              marginBottom: 10,
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                            }}
                          >
                            <Title level={5}>生成结果</Title>
                            {image.isGenerating && (
                              <div>
                                <Spin size="small" style={{ marginRight: 8 }} />
                                <Text type="secondary">
                                  正在生成3张图片，请稍候...
                                </Text>
                              </div>
                            )}
                          </div>
                        </Col>
                      </Row>

                      {image.isGenerating ? (
                        <Row gutter={16}>
                          {[1, 2, 3].map((_, index) => (
                            <Col span={8} key={index}>
                              <Card style={{ height: 260 }}>
                                <div
                                  style={{
                                    height: 200,
                                    display: "flex",
                                    justifyContent: "center",
                                    alignItems: "center",
                                    background: "#f5f5f5",
                                  }}
                                >
                                  <Spin size="large" />
                                </div>
                                <div
                                  style={{ textAlign: "center", marginTop: 10 }}
                                >
                                  <Text type="secondary">生成中...</Text>
                                </div>
                              </Card>
                            </Col>
                          ))}
                        </Row>
                      ) : (
                        <Row gutter={16}>
                          {generatedImages[image.file_path]
                            ?.slice(0, 3)
                            .map((genImage, index) => (
                              <Col span={8} key={genImage.id || index}>
                                <Card
                                  hoverable
                                  cover={
                                    <div
                                      style={{
                                        height: 200,
                                        overflow: "hidden",
                                        position: "relative",
                                      }}
                                    >
                                      <img
                                        src={
                                          useMockData
                                            ? `/example-generated-${
                                                (index % 3) + 1
                                              }.jpg`
                                            : genImage.result_image_path && genImage.result_image_path.startsWith(
                                                "http"
                                              )
                                            ? genImage.result_image_path
                                            : `${api.defaults.baseURL}/${genImage.result_image_path || ""}`
                                        }
                                        alt={`生成图片 ${index + 1}`}
                                        style={{
                                          width: "100%",
                                          height: "100%",
                                          objectFit: "cover",
                                          cursor: "pointer",
                                        }}
                                        onClick={() => {
                                          const imgUrl = useMockData
                                            ? `/example-generated-${
                                                (index % 3) + 1
                                              }.jpg`
                                            : genImage.result_image_path && genImage.result_image_path.startsWith(
                                                "http"
                                              )
                                            ? genImage.result_image_path
                                            : `${api.defaults.baseURL}/${genImage.result_image_path || ""}`;
                                          setPreviewImage(imgUrl);
                                          setPreviewTitle(
                                            `生成图片 版本 ${
                                              generatedImages[image.file_path]
                                                ?.length - index
                                            }`
                                          );
                                          setPreviewVisible(true);
                                        }}
                                      />
                                      <div
                                        style={{
                                          position: "absolute",
                                          top: 0,
                                          right: 0,
                                          backgroundColor: "rgba(0, 0, 0, 0.6)",
                                          color: "white",
                                          padding: "4px 8px",
                                          borderBottomLeftRadius: "8px",
                                          fontSize: "12px",
                                          fontWeight: "bold",
                                        }}
                                      >
                                        版本{" "}
                                        {generatedImages[image.file_path]
                                          ?.length - index}
                                      </div>
                                    </div>
                                  }
                                >
                                  <div style={{ textAlign: "center" }}>
                                    <div
                                      style={{
                                        fontWeight: "bold",
                                        marginBottom: 5,
                                      }}
                                    >
                                      Seed:{" "}
                                      {genImage.seed ||
                                        Math.floor(Math.random() * 1000000)}
                                    </div>
                                    <div
                                      style={{
                                        fontSize: "12px",
                                        color: "#888",
                                        marginTop: "4px",
                                        marginBottom: "8px",
                                      }}
                                    >
                                      {new Date(
                                        genImage.created_at
                                      ).toLocaleString()}
                                    </div>
                                    <div>
                                      <Text type="secondary">
                                        模型: {genImage.model_name}
                                      </Text>
                                    </div>
                                    <div
                                      style={{
                                        marginTop: "8px",
                                        display: "flex",
                                        justifyContent: "space-between",
                                      }}
                                    >
                                      <Button
                                        size="small"
                                        onClick={async () => {
                                          try {
                                            message.loading(
                                              "正在重新生成图片...",
                                              0
                                            );
                                            const newSeed = Math.floor(
                                              Math.random() * 1000000
                                            );

                                            const response = await api.post(
                                              "/api/generation/image-to-image",
                                              {
                                                model_id: selectedModel,
                                                image_url: `${
                                                  api.defaults.baseURL
                                                }/uploads/${genImage.source_image_path.replace(
                                                  /^uploads\//,
                                                  ""
                                                )}`,
                                                prompt: genImage.prompt,
                                                project_id: selectedProject,
                                                seed: newSeed,
                                              }
                                            );

                                            // 获取优化后的提示词 (只用于生成结果记录，不更新到状态)
                                            const optimizedPrompt =
                                              response.data.prompt ||
                                              genImage.prompt;

                                            // 创建新图片对象并添加到列表开头 (这里仍然使用API返回的优化提示词)
                                            const newGeneratedImage = {
                                              id: response.data.id,
                                              prompt: optimizedPrompt, // 使用API返回的优化提示词
                                              model_name: genImage.model_name,
                                              result_image_path:
                                                response.data.image_url.replace(
                                                  `${api.defaults.baseURL}/`,
                                                  ""
                                                ),
                                              source_image_path:
                                                genImage.source_image_path,
                                              created_at:
                                                new Date().toISOString(),
                                              seed: newSeed,
                                            };

                                            // 更新所有相关列表
                                            setGeneratedImages((prev) => ({
                                              ...prev,
                                              [genImage.source_image_path]: [
                                                newGeneratedImage,
                                                ...prev[
                                                  genImage.source_image_path
                                                ],
                                              ],
                                            }));

                                            if (modalVisible) {
                                              setCurrentGeneratedImages(
                                                (prev) => [
                                                  newGeneratedImage,
                                                  ...prev,
                                                ]
                                              );
                                            }

                                            if (
                                              viewingGenerationsFor ===
                                              genImage.source_image_path
                                            ) {
                                              setCurrentImageGenerations(
                                                (prev) => [
                                                  newGeneratedImage,
                                                  ...prev,
                                                ]
                                              );
                                            }

                                            message.destroy();
                                            message.success("已生成新图片");
                                          } catch (error) {
                                            message.destroy();
                                            console.error(
                                              "重新生成失败:",
                                              error
                                            );
                                            message.error("重新生成失败");
                                          }
                                        }}
                                      >
                                        随机Seed
                                      </Button>
                                      <Button
                                        size="small"
                                        type="primary"
                                        onClick={() => {
                                          // 查找原始图片
                                          const sourceImage = images.find(
                                            (img) =>
                                              img.file_path ===
                                              genImage.source_image_path
                                          );
                                          if (sourceImage) {
                                            setCurrentEditingImage(sourceImage);
                                            setCurrentEditingGeneratedImage(
                                              genImage
                                            );

                                            // 查找当前模型ID
                                            const modelId =
                                              models.find(
                                                (m) =>
                                                  m.alias ===
                                                  genImage.model_name
                                              )?.id || selectedModel;

                                            // 优先使用imagePrompts中的提示词
                                            const currentPrompt = sourceImage
                                              ? imagePrompts[sourceImage.id] ||
                                                genImage.prompt
                                              : genImage.prompt;

                                            adjustGeneratedImageForm.setFieldsValue(
                                              {
                                                model_id: modelId,
                                                prompt: currentPrompt,
                                                seed:
                                                  genImage.seed ||
                                                  Math.floor(
                                                    Math.random() * 1000000
                                                  ),
                                              }
                                            );
                                            setAdjustGeneratedImageModalVisible(
                                              true
                                            );
                                          } else {
                                            message.error("找不到原始图片");
                                          }
                                        }}
                                      >
                                        调整参数
                                      </Button>
                                    </div>
                                  </div>
                                </Card>
                              </Col>
                            ))}

                          {(!generatedImages[image.file_path] ||
                            generatedImages[image.file_path].length === 0) && (
                            <Col span={24}>
                              <Empty description="暂无生成结果" />
                            </Col>
                          )}
                        </Row>
                      )}

                      {generatedImages[image.file_path]?.length > 3 && (
                        <div style={{ textAlign: "center", marginTop: 16 }}>
                          <Button
                            type="link"
                            icon={<EyeOutlined />}
                            onClick={() =>
                              showAllGeneratedImages(
                                image.file_path,
                                generatedImages[image.file_path]
                              )
                            }
                          >
                            查看更多 ({generatedImages[image.file_path].length}){" "}
                            <RightOutlined />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </Col>
              </Row>
            </Card>
          ))}

          <div style={{ textAlign: "center", marginTop: 20 }}>
            <Pagination
              current={currentPage}
              pageSize={pageSize}
              total={totalImages}
              onChange={handlePageChange}
              onShowSizeChange={handlePageSizeChange}
              showSizeChanger
              showQuickJumper
              showTotal={(total) => `共 ${total} 张图片`}
            />
          </div>
        </div>
      )}

      {/* 查看所有生成图片的模态框 */}
      <Modal
        title="所有生成图片"
        visible={modalVisible}
        onCancel={() => setModalVisible(false)}
        width={1000}
        footer={null}
        zIndex={1000}
      >
        <div style={{ marginBottom: 20 }}>
          <div style={{ textAlign: "center", marginBottom: 20 }}>
            <div
              style={{
                border: "1px solid #e0e0e0",
                borderRadius: "8px",
                padding: "12px",
                backgroundColor: "#f9f9f9",
                display: "inline-block",
                maxWidth: "100%",
                position: "relative",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  right: 0,
                  backgroundColor: "rgba(0, 0, 0, 0.6)",
                  color: "white",
                  padding: "4px 8px",
                  borderTopRightRadius: "8px",
                  borderBottomLeftRadius: "8px",
                  fontSize: "12px",
                  fontWeight: "bold",
                  zIndex: 1,
                }}
              >
                原始图片
              </div>
              <img
                src={
                  useMockData
                    ? `/example-image.jpg`
                    : `${
                        api.defaults.baseURL
                      }/uploads/${currentImagePath.replace(/^uploads\//, "")}`
                }
                alt="原始图片"
                style={{
                  maxHeight: 200,
                  objectFit: "contain",
                  cursor: "pointer",
                }}
                onClick={() => {
                  const imgUrl = useMockData
                    ? `/example-image.jpg`
                    : `${
                        api.defaults.baseURL
                      }/uploads/${currentImagePath.replace(/^uploads\//, "")}`;
                  setPreviewImage(imgUrl);
                  setPreviewTitle(
                    currentImagePath.split("/").pop() || "原始图片"
                  );
                  setPreviewVisible(true);
                }}
              />
              <div
                style={{
                  marginTop: 10,
                  display: "flex",
                  justifyContent: "space-between",
                }}
              >
                <Button
                  type="primary"
                  icon={<PictureOutlined />}
                  onClick={() => {
                    // 查找原始图片对象
                    const sourceImage = images.find(
                      (img) => img.file_path === currentImagePath
                    );
                    if (sourceImage) {
                      handleGenerateImage(sourceImage);
                    } else {
                      message.error("找不到原始图片");
                    }
                    setModalVisible(false); // 关闭当前模态框
                  }}
                >
                  生成图片
                </Button>
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => {
                    // 查找原始图片对象
                    const sourceImage = images.find(
                      (img) => img.file_path === currentImagePath
                    );
                    if (sourceImage) {
                      handleDeleteImage(sourceImage.id);
                      setModalVisible(false); // 关闭当前模态框
                    } else {
                      message.error("找不到原始图片");
                    }
                  }}
                >
                  删除图片
                </Button>
              </div>
            </div>
          </div>

          <Divider>生成结果 ({currentGeneratedImages.length})</Divider>

          <Row gutter={[16, 16]}>
            {currentGeneratedImages.map((genImage, index) => (
              <Col span={8} key={genImage.id || index}>
                <Card bordered>
                  <div style={{ textAlign: "center", position: "relative" }}>
                    <img
                      src={
                        useMockData
                          ? `/example-generated-${(index % 3) + 1}.jpg`
                          : genImage.result_image_path && genImage.result_image_path.startsWith(
                              "http"
                            )
                          ? genImage.result_image_path
                          : `${api.defaults.baseURL}/${genImage.result_image_path || ""}`
                      }
                      alt={`生成图片 ${index + 1}`}
                      style={{
                        width: "100%",
                        height: 180,
                        objectFit: "cover",
                        cursor: "pointer",
                      }}
                      onClick={() => {
                        const imgUrl = useMockData
                          ? `/example-generated-${(index % 3) + 1}.jpg`
                          : genImage.result_image_path && genImage.result_image_path.startsWith(
                              "http"
                            )
                          ? genImage.result_image_path
                          : `${api.defaults.baseURL}/${genImage.result_image_path || ""}`;
                        setPreviewImage(imgUrl);
                        setPreviewTitle(
                          `生成图片 版本 ${
                            currentGeneratedImages.length - index
                          }`
                        );
                        setPreviewVisible(true);
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        right: 0,
                        backgroundColor: "rgba(0, 0, 0, 0.6)",
                        color: "white",
                        padding: "4px 8px",
                        borderBottomLeftRadius: "8px",
                        fontSize: "12px",
                        fontWeight: "bold",
                      }}
                    >
                      版本 {currentGeneratedImages.length - index}
                    </div>
                  </div>
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontWeight: "bold", marginBottom: 5 }}>
                      Seed:{" "}
                      {genImage.seed || Math.floor(Math.random() * 1000000)}
                    </div>
                    <div
                      style={{
                        fontSize: "12px",
                        color: "#888",
                        marginTop: "4px",
                        marginBottom: "8px",
                      }}
                    >
                      {new Date(genImage.created_at).toLocaleString()}
                    </div>
                    <div>
                      <Text type="secondary">模型: {genImage.model_name}</Text>
                    </div>
                    <div
                      style={{
                        marginTop: "8px",
                        display: "flex",
                        justifyContent: "space-between",
                      }}
                    >
                      <Button
                        size="small"
                        onClick={async () => {
                          try {
                            message.loading("正在重新生成图片...", 0);
                            const newSeed = Math.floor(Math.random() * 1000000);

                            const response = await api.post(
                              "/api/generation/image-to-image",
                              {
                                model_id: selectedModel,
                                image_url: `${
                                  api.defaults.baseURL
                                }/uploads/${genImage.source_image_path.replace(
                                  /^uploads\//,
                                  ""
                                )}`,
                                prompt: genImage.prompt,
                                project_id: selectedProject,
                                seed: newSeed,
                              }
                            );

                            // 获取优化后的提示词 (只用于生成结果记录，不更新到状态)
                            const optimizedPrompt =
                              response.data.prompt || genImage.prompt;

                            // 创建新图片对象并添加到列表开头 (这里仍然使用API返回的优化提示词)
                            const newGeneratedImage = {
                              id: response.data.id,
                              prompt: optimizedPrompt, // 使用API返回的优化提示词
                              model_name: genImage.model_name,
                              result_image_path:
                                response.data.image_url.replace(
                                  `${api.defaults.baseURL}/`,
                                  ""
                                ),
                              source_image_path: genImage.source_image_path,
                              created_at: new Date().toISOString(),
                              seed: newSeed,
                            };

                            // 更新所有相关列表
                            setGeneratedImages((prev) => ({
                              ...prev,
                              [genImage.source_image_path]: [
                                newGeneratedImage,
                                ...prev[genImage.source_image_path],
                              ],
                            }));

                            if (modalVisible) {
                              setCurrentGeneratedImages((prev) => [
                                newGeneratedImage,
                                ...prev,
                              ]);
                            }

                            if (
                              viewingGenerationsFor ===
                              genImage.source_image_path
                            ) {
                              setCurrentImageGenerations((prev) => [
                                newGeneratedImage,
                                ...prev,
                              ]);
                            }

                            message.destroy();
                            message.success("已生成新图片");
                          } catch (error) {
                            message.destroy();
                            console.error("重新生成失败:", error);
                            message.error("重新生成失败");
                          }
                        }}
                      >
                        随机Seed
                      </Button>
                      <Button
                        size="small"
                        type="primary"
                        onClick={() => {
                          // 查找原始图片
                          const sourceImage = images.find(
                            (img) =>
                              img.file_path === genImage.source_image_path
                          );
                          if (sourceImage) {
                            setCurrentEditingImage(sourceImage);
                            setCurrentEditingGeneratedImage(genImage);

                            // 查找当前模型ID
                            const modelId =
                              models.find(
                                (m) => m.alias === genImage.model_name
                              )?.id || selectedModel;

                            // 优先使用imagePrompts中的提示词
                            const currentPrompt = sourceImage
                              ? imagePrompts[sourceImage.id] || genImage.prompt
                              : genImage.prompt;

                            adjustGeneratedImageForm.setFieldsValue({
                              model_id: modelId,
                              prompt: currentPrompt,
                              seed:
                                genImage.seed ||
                                Math.floor(Math.random() * 1000000),
                            });
                            setAdjustGeneratedImageModalVisible(true);
                          } else {
                            message.error("找不到原始图片");
                          }
                        }}
                      >
                        调整参数
                      </Button>
                    </div>
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
        </div>
      </Modal>

      {/* 编辑提示词模态框 */}
      <Modal
        title="编辑图片提示词"
        visible={promptModalVisible}
        onCancel={() => setPromptModalVisible(false)}
        footer={null}
        zIndex={1050}
      >
        <Form
          form={promptForm}
          layout="vertical"
          onFinish={(values) => {
            if (currentEditingImage) {
              // 保存提示词到对应图片
              setImagePrompts((prev) => ({
                ...prev,
                [currentEditingImage.id]: values.prompt,
              }));
              message.success("提示词已保存");
              setPromptModalVisible(false);
            }
          }}
        >
          <Form.Item
            name="prompt"
            label="提示词"
            rules={[{ required: true, message: "请输入提示词" }]}
            extra="提示词用于指导AI生成图片，编辑后将应用于该图片的所有后续生成"
          >
            <TextArea rows={6} placeholder="请输入提示词，用于指导AI生成图片" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              保存提示词
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 调整生成图片模态框 */}
      <Modal
        title="调整生成参数"
        visible={adjustGeneratedImageModalVisible}
        onCancel={() => setAdjustGeneratedImageModalVisible(false)}
        footer={null}
        zIndex={1050}
      >
        <Form
          form={adjustGeneratedImageForm}
          layout="vertical"
          onFinish={async (values) => {
            if (currentEditingGeneratedImage) {
              try {
                message.loading("正在生成新图片...", 0);
                const response = await api.post(
                  "/api/generation/image-to-image",
                  {
                    model_id: values.model_id,
                    image_url: `${
                      api.defaults.baseURL
                    }/uploads/${currentEditingGeneratedImage.source_image_path.replace(
                      /^uploads\//,
                      ""
                    )}`,
                    prompt: values.prompt,
                    project_id: selectedProject,
                    seed: values.seed,
                  }
                );

                // 获取优化后的提示词 (只用于生成结果记录，不更新到状态)
                const optimizedPrompt = response.data.prompt || values.prompt;

                // 保存用户输入的提示词到状态（不使用API返回的优化提示词）
                if (currentEditingImage) {
                  setImagePrompts((prev) => ({
                    ...prev,
                    [currentEditingImage.id]: values.prompt,
                  }));
                }

                // 创建新图片对象并添加到列表开头
                const newGeneratedImage = {
                  id: response.data.id,
                  prompt: optimizedPrompt, // 使用API返回的优化提示词
                  model_name:
                    models.find((m) => m.id === values.model_id)?.alias ||
                    "未知模型",
                  result_image_path: response.data.image_url.replace(
                    `${api.defaults.baseURL}/`,
                    ""
                  ),
                  source_image_path:
                    currentEditingGeneratedImage.source_image_path,
                  created_at: new Date().toISOString(),
                  seed: values.seed,
                };

                // 更新所有相关状态
                setGeneratedImages((prev) => ({
                  ...prev,
                  [currentEditingGeneratedImage.source_image_path]: [
                    newGeneratedImage,
                    ...prev[currentEditingGeneratedImage.source_image_path],
                  ],
                }));

                if (modalVisible) {
                  setCurrentGeneratedImages((prev) => [
                    newGeneratedImage,
                    ...prev,
                  ]);
                }

                if (
                  viewingGenerationsFor ===
                  currentEditingGeneratedImage.source_image_path
                ) {
                  setCurrentImageGenerations((prev) => [
                    newGeneratedImage,
                    ...prev,
                  ]);
                }

                message.destroy();
                message.success("已生成新图片");
                setAdjustGeneratedImageModalVisible(false);
              } catch (error) {
                message.destroy();
                console.error("生成失败:", error);
                message.error("生成失败");
              }
            }
          }}
        >
          <Form.Item
            name="model_id"
            label="选择模型"
            rules={[{ required: true, message: "请选择模型" }]}
          >
            <Select placeholder="请选择模型">
              {models.map((model) => (
                <Option key={model.id} value={model.id}>
                  {model.alias}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="prompt"
            label="提示词"
            rules={[{ required: true, message: "请输入提示词" }]}
          >
            <TextArea rows={6} placeholder="请输入提示词，用于指导AI生成图片" />
          </Form.Item>

          <Form.Item
            name="seed"
            label="种子值"
            rules={[{ required: true, message: "请输入种子值" }]}
          >
            <Input type="number" placeholder="请输入种子值" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              重新生成图片
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加图片预览模态框 */}
      <Modal
        visible={previewVisible}
        title={previewTitle}
        footer={null}
        onCancel={() => setPreviewVisible(false)}
        width="80%"
        zIndex={1100}
      >
        <div style={{ textAlign: "center" }}>
          <img
            alt={previewTitle}
            style={{ maxWidth: "100%", maxHeight: "80vh" }}
            src={previewImage}
          />
        </div>
      </Modal>

      {/* 队列并发设置模态框 */}
      <Modal
        title="批量生成队列设置"
        visible={queueSettingsModalVisible}
        onCancel={() => setQueueSettingsModalVisible(false)}
        footer={[
          <Button
            key="cancel"
            onClick={() => setQueueSettingsModalVisible(false)}
          >
            取消
          </Button>,
          <Button
            key="submit"
            type="primary"
            onClick={() => {
              submitBatchGenerationQueue(concurrency);
              setQueueSettingsModalVisible(false);
            }}
          >
            开始生成
          </Button>,
        ]}
      >
        <div>
          <div style={{ marginBottom: 16 }}>
            <Text>选择并发数量（1-10）:</Text>
            <Slider
              min={1}
              max={10}
              value={concurrency}
              onChange={(value) => setConcurrency(value)}
              marks={{
                1: "1",
                5: "5",
                10: "10",
              }}
            />
            <div style={{ textAlign: "center", marginTop: 8 }}>
              <Text type="secondary">当前设置: {concurrency} 个并发请求</Text>
            </div>
          </div>
          <Alert
            type="info"
            message="批量生成说明"
            description={
              <div>
                <p>系统将为每张选中的图片生成<b>3个不同随机种子</b>的变体，共计 {selectedImages.length} × 3 = <b>{selectedImages.length * 3}</b> 张图片。</p>
                <p>并发数越高，批量生成速度越快，但可能会影响系统性能。默认值5适合大多数情况。</p>
                <p>所有图片将添加到Redis队列中，您可以随时查看生成进度。</p>
              </div>
            }
            style={{ marginBottom: 16 }}
          />
          <div style={{ textAlign: 'center' }}>
            <Text strong>
              预计生成总数: {selectedImages.length * 3} 张图片
            </Text>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default ProjectGallery;
