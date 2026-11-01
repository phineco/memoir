# 家音品牌图标

2026-11-01：Louis 确认“深绿底、米白屋檐与声波”方案并授权接入、本地提交。母版由内置 imagegen 生成，原图保存为本目录 jiayin-master.png；派生文件只做尺寸导出，未改变图案。

浏览器使用16/32像素PNG和包含16/32/48像素的ICO，Apple桌面图标180像素，PWA安装图标192/512像素。源文件位于 static/icons/jiayin-*.png 与 static/icons/favicon.ico，构建时由 tools/frontend.py 生成带内容指纹的文件，模板及manifest均引用构建产物。图标随公共静态资源进入PWA白名单；不缓存私人家庭资料。旧easy-*.png保留，兼容旧客户端。

导出使用macOS sips保持正方形并缩放为目标尺寸；ICO容器嵌入已导出的PNG。所有PNG为不透明背景。192/512像素图案的米白区域均在半径40%的中心安全圆内，满足当前maskable圆形裁切；系统最终外形及已安装图标刷新时机仍由设备决定。

完整版和简易版共用网站图标及Apple桌面图标声明，/favicon.ico重定向至带指纹的ICO。PWA仍由原有开关控制；本次不启用安装能力、不增加配置或数据库迁移。静态资源检查、18项相关后端检查、9组页面布局及PWA缓存/受控更新/离线隐私/切账号浏览器回归通过，尚未进行华为真机安装验收。

## 生成提示词

Use case: logo-brand. Create ONE polished production-ready square master icon for the Chinese family memoir product 家音 (family voices and memories). It will be used both as a tiny browser favicon and a mobile home-screen app icon for older adults. Design a single extremely simple, distinctive flat vector-style symbol: a warm ivory house-roof silhouette sheltering THREE bold rounded vertical sound-wave bars, balanced short/tall/medium, integrated into one cohesive home-and-voice emblem. A subtle gentle curve at the base may connect the bars, only if it improves the mark. Minimal geometric shapes, substantial thickness, generous clean negative space, warm and trustworthy, not technical or corporate. Brand palette: full-bleed solid deep forest green #245E49 across the ENTIRE square canvas; emblem warm ivory #FFF8E9. Center the symbol and keep all essential artwork within the central 70 percent of the canvas so Android maskable circle/squircle crops preserve it. The background must extend to every edge; NO pre-rounded outer rectangle, NO border, NO surrounding whitespace. Flat solid colors, crisp edges, optically balanced, designed to remain clear at 16x16 and 32x32. Absolutely NO text, NO Chinese characters, NO letters, NO numbers, NO tagline, NO watermark, NO mockup, NO grids, NO extra variants. No microphone, no headphones, no Wi-Fi symbol, no intricate decorative details, no gradients, no 3D, no shadows. A single large square icon only, approximately 1024x1024.
