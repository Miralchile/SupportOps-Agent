import { Router } from '@/router'
import { App as AntdApp, ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/es/locale/zh_CN'
import { useCallback, useRef, useState } from 'react'
function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        cssVar: true,
        token: {
          colorPrimary: '#3157d5',
          colorInfo: '#3157d5',
          colorSuccess: '#12805c',
          colorWarning: '#b15c11',
          colorError: '#c13b32',
          colorText: '#182230',
          colorTextSecondary: '#667085',
          colorBorder: '#d9e0e8',
          colorBgLayout: '#f4f6f8',
          borderRadius: 8,
          borderRadiusLG: 12,
          controlHeight: 38,
          fontFamily:
            'Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <AntdApp>
        <Router />
        <MountApi />
      </AntdApp>
    </ConfigProvider>
  )
}

function MountApi() {
  window.$app = AntdApp.useApp()

  const [loading, setLoading] = useState(false)
  const [loadingText, setLoadingText] = useState('')
  const loadingCount = useRef(0)
  window.$showLoading = useCallback(({ title }: { title?: string } = {}) => {
    loadingCount.current++
    setLoading(true)
    setLoadingText(title ?? '')
  }, [])
  window.$hideLoading = useCallback(() => {
    loadingCount.current--
    setTimeout(() => {
      if (loadingCount.current <= 0) {
        setLoading(false)
        setLoadingText('')
      }
    }, 100)
  }, [])

  return (
    <>
      <Spin
        spinning={loading}
        tip={loadingText}
        fullscreen
        style={{
          zIndex: 9999999,
        }}
      ></Spin>
    </>
  )
}

export default App
