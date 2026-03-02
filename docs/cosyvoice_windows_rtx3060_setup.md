# CosyVoice (Windows RTX 3060) 本地部署与启动指南

由于网络或系统环境原因，请依照本指南通过 Conda 初始化您的本地 CosyVoice 语音克隆和合成大模型服务。我们已在系统中集成 `tts_client.py` 关联此本地推理引擎（FastAPI 形式）。

## 第一步：准备环境 (Conda 方式)

1. 打开 Windows 端的 **Anaconda Prompt**，进入 CosyVoice 仓库目录：
   ```cmd
   cd C:\docker\Myavatar\CosyVoice
   ```

2. 创建 Python 3.10 环境并激活：
   ```cmd
   conda create -n cosyvoice python=3.10 -y
   conda activate cosyvoice
   ```

3. 安装必要的 C++ 和音视频组件（Linux 需要 ffmpeg，Windows 端可以用 conda 安装 pynini 和 ffmpeg）：
   ```cmd
   conda install -y -c conda-forge pynini==2.1.5
   conda install -y -c conda-forge ffmpeg
   ```

4. 安装 Python 核心依赖项：
   ```cmd
   pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
   ```

5. (非常关键 - 因显卡是 RTX 3060 12G) 安装 Pytorch CUDA 11.8/12.1 版本。根据您目前的 CUDA 版本，运行：
   *(以下命令假设使用 CUDA 11.8 为例)*
   ```cmd
   pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

## 第二步：下载运行级模型 (ModelScope)

为了让 CosyVoice 运作，需要拉取官方开源的模型文件。
在同一个终端下运行 Python 脚本或者执行：

```cmd
git lfs install
git clone https://www.modelscope.cn/iic/CosyVoice-300M.git pretrained_models/CosyVoice-300M
git clone https://www.modelscope.cn/iic/CosyVoice-300M-SFT.git pretrained_models/CosyVoice-300M-SFT
git clone https://www.modelscope.cn/iic/CosyVoice-300M-Instruct.git pretrained_models/CosyVoice-300M-Instruct
```
*备注：考虑到网络情况，部分模型可能会比较大（1-2GB），请耐心等待。*

## 第三步：启动 FastAPI 服务接口

当所有库与模型都准备好后，在 CosyVoice 仓库目录下启动推理服务端口。

```cmd
python runtime/python/fastapi/server.py --port 50000 --max_client 4
```

如果启动成功，终端会显示运行在 `http://127.0.0.1:50000` 或 `http://0.0.0.0:50000`。

## 第四步：检查我们的工作流配置
在我们 Myavatar 工具根目录下的 `.env` 中，确保以下值已经填写好，系统会自动通过 Node 4 `n4_tts_synthesizer.py` 寻找这个本地接口：

```env
AUDIO_SOURCE_MODE=cosyvoice
COSYVOICE_API_STYLE=official_fastapi
COSYVOICE_API_URL=http://localhost:50000
COSYVOICE_MODE=sft
COSYVOICE_VOICE=中文女
```

> **注意：**如果您的显存不够（OOM），可能需要修改 `server.py` 或降低并发数。不过 12G 显存运行 CosyVoice-300M 模型是绰绰有余的。
