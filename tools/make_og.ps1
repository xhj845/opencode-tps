Add-Type -AssemblyName System.Drawing

$W = 1200
$H = 630
$bmp = New-Object System.Drawing.Bitmap $W, $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

$bg = [System.Drawing.ColorTranslator]::FromHtml('#070b10')
$g.Clear($bg)

$gridPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(18, 255, 255, 255)), 1
for ($x = 0; $x -lt $W; $x += 60) { $g.DrawLine($gridPen, $x, 0, $x, $H) }
for ($y = 0; $y -lt $H; $y += 60) { $g.DrawLine($gridPen, 0, $y, $W, $y) }

for ($i = 14; $i -ge 1; $i--) {
    $alpha = [int](2 + (14 - $i) * 0.9)
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb($alpha, 74, 222, 128))
    $size = 170 + $i * 20
    $g.FillEllipse($brush, 855 - $size / 2, 315 - $size / 2, $size, $size)
    $brush.Dispose()
}

$accent = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#4ade80')), 3
$g.DrawLine($accent, 80, 176, 190, 176)

$mono = [System.Drawing.Font]::new('Consolas', 15, [System.Drawing.FontStyle]::Regular)
$muted = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#93a4b8'))
$dim = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#64758a'))
$white = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#e9f0f8'))
$green = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#4ade80'))
$g.DrawString('OPENCODE  /  OPENCHAMBER COMPATIBLE  /  LOCAL PLUGIN', $mono, $muted, 80, 146)

$title = [System.Drawing.Font]::new('Consolas', 58, [System.Drawing.FontStyle]::Bold)
$g.DrawString('OpenCode TPS', $title, $white, 72, 206)

$sub = [System.Drawing.Font]::new('Segoe UI', 34, [System.Drawing.FontStyle]::Bold)
$g.DrawString('tok/s at a glance.', $sub, $white, 76, 322)

$body = [System.Drawing.Font]::new('Segoe UI', 18, [System.Drawing.FontStyle]::Regular)
$g.DrawString('Live floating ball  /  Multi-session  /  OpenChamber compatible', $body, $muted, 78, 390)
$g.DrawString('Windows 10/11  /  Python 3.10+  /  Local-first', $mono, $dim, 78, 432)

$chipFont = [System.Drawing.Font]::new('Consolas', 14, [System.Drawing.FontStyle]::Bold)
$chipRect = New-Object System.Drawing.Rectangle 78, 500, 250, 36
$chipPath = New-Object System.Drawing.Drawing2D.GraphicsPath
$chipPath.AddArc($chipRect.X, $chipRect.Y, 18, 18, 180, 90)
$chipPath.AddArc($chipRect.Right - 18, $chipRect.Y, 18, 18, 270, 90)
$chipPath.AddArc($chipRect.Right - 18, $chipRect.Bottom - 18, 18, 18, 0, 90)
$chipPath.AddArc($chipRect.X, $chipRect.Bottom - 18, 18, 18, 90, 90)
$chipPath.CloseFigure()
$chipBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(22, 74, 222, 128))
$chipPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(80, 74, 222, 128)), 1
$g.FillPath($chipBrush, $chipPath)
$g.DrawPath($chipPen, $chipPath)
$g.DrawString('v1.2.0  /  15 KB', $chipFont, $green, 92, 508)

$ballBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#0b1118'))
$ringPen = New-Object System.Drawing.Pen ([System.Drawing.ColorTranslator]::FromHtml('#4ade80')), 4
$g.FillEllipse($ballBrush, 795, 245, 210, 210)
$g.DrawEllipse($ringPen, 795, 245, 210, 210)
$ringPen2 = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(60, 74, 222, 128)), 2
$g.DrawEllipse($ringPen2, 781, 231, 238, 238)

$speedFont = [System.Drawing.Font]::new('Consolas', 64, [System.Drawing.FontStyle]::Bold)
$unitFont = [System.Drawing.Font]::new('Consolas', 16, [System.Drawing.FontStyle]::Regular)
$sf = $g.MeasureString('142', $speedFont)
$g.DrawString('142', $speedFont, $white, 900 - $sf.Width / 2, 312)
$uf = $g.MeasureString('/ tok/s', $unitFont)
$g.DrawString('/ tok/s', $unitFont, $muted, 900 - $uf.Width / 2, 390)

$badgeBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml('#4ade80'))
$g.FillEllipse($badgeBrush, 970, 245, 44, 44)
$badgeFont = [System.Drawing.Font]::new('Consolas', 18, [System.Drawing.FontStyle]::Bold)
$bgBrush = New-Object System.Drawing.SolidBrush $bg
$g.DrawString('2', $badgeFont, $bgBrush, 983, 251)

$bmp.Save((Join-Path $PSScriptRoot '..\dist\assets\og.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
$g.Dispose()
Write-Output 'og saved'
