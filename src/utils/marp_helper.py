import os
import subprocess
from pathlib import Path
from typing import List, Optional

def render_markdown_to_images(
    markdown_content: str, 
    output_dir: str, 
    theme_path: Optional[str] = None
) -> List[str]:
    """
    使用 marp-cli 将 Markdown 文本渲染为按顺序命名的超高清静态图片序列。
    需要宿主机安装 Node.js 和 @marp-team/marp-cli
        npm install -g @marp-team/marp-cli
    """
    os.makedirs(output_dir, exist_ok=True)
    temp_md_path = Path(output_dir) / "temp_input.md"
    
    with open(temp_md_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
        
    cmd = [
        "marp", 
        str(temp_md_path),
        "--images", "png",
        "--output", str(Path(output_dir) / "slide_%03d.png")
    ]
    
    if theme_path and os.path.exists(theme_path):
        cmd.extend(["--theme", theme_path])
        
    try:
        print(f"Executing Marp: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, capture_output=True, text=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Marp render failed: {e.stderr}")
        raise
        
    # Collect generated images
    images = sorted([
        str(p) for p in Path(output_dir).glob("slide_*.png")
    ])
    
    # 清理临时文件
    if temp_md_path.exists():
        temp_md_path.unlink()
        
    return images

if __name__ == "__main__":
    sample_md = """---
marp: true
---

# 欢迎使用视频自动生成管线
这是第一页测试幻灯片

---

## 核心特性
1. **代码驱动**：Video-as-Code 理念
2. **多模态对齐**：绝对时间的音画同步
3. **极速渲染**：告别逐帧计算
"""
    test_out = "c:/docker/Myavatar/workspace/task_test/marp_output"
    print("Testing Marp render...")
    res = render_markdown_to_images(sample_md, test_out)
    print(f"Generated images: {res}")
