// 验证码识别模块（轻量版 - 不依赖 ddddocr）
// ddddocr 已从 Docker 镜像中移除以减小体积
// 如需验证码识别功能，可在本地环境安装 ddddocr

export async function solveCaptcha(imgBase64: string): Promise<string> {
  console.log("[captcha] ddddocr 未安装，跳过验证码识别");
  return "";
}

export async function isCaptchaAvailable(): Promise<boolean> {
  return false;
}
