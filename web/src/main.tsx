import { render } from 'preact';
import { App } from './app';
import { loadModel, Model } from './model';
import './styles.css';

async function start() {
  let model = loadModel();
  if (!model && import.meta.env.DEV) model = (await (await fetch('/model.json')).json()) as Model;
  const root = document.getElementById('app')!;
  if (!model) { root.textContent = '没有找到阅读模型数据。请用 build_reader_dashboard.py 生成页面。'; return; }
  render(<App model={model} />, root);
}
start();
