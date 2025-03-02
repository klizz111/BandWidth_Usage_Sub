import os
import base64
import subprocess
from datetime import datetime
from ruamel.yaml import YAML
from xml.etree import ElementTree as ET
from dotenv import load_dotenv
from github import Github, GithubException, Auth, InputGitTreeElement

def get_bandwidth_usage():
    """获取当月流量使用情况"""
    vnstat = os.popen('vnstat --xml m').read()
    tree = ET.fromstring(vnstat)
    traffic = tree.find("interface").find("traffic")

    current_year = datetime.now().year
    current_month = datetime.now().month
    current_day = datetime.now().day
    rx = tx = 0

    # 查找当月数据
    for month_data in traffic.find("months").iter("month"):
        date = month_data.find("date")
        if date is None:
            continue
            
        year_node = date.find("year")
        month_node = date.find("month")
        if year_node is None or month_node is None:
            continue
            
        if (int(year_node.text) == current_year and int(month_node.text) == current_month):
            rx = int(month_data.find("rx").text)
            tx = int(month_data.find("tx").text)
            break
    
    # 计算总流量(GB)        
    total = round((rx + tx) / 1024 / 1024 / 1024, 2)

    # 计算昨日使用量
    vnstat = os.popen('vnstat --xml d').read()
    tree = ET.fromstring(vnstat)
    traffic = tree.find("interface").find("traffic")

    # 查找昨日数据
    for day_data in traffic.find("days").iter("day"):
        date = day_data.find("date")
        if date is None:
            continue
        year_node = date.find("year")
        month_node = date.find("month")
        day_node = date.find("day")
        if year_node is None or month_node is None or day_node is None:
            continue
        if (int(year_node.text) == current_year and int(month_node.text) == current_month and int(day_node.text) == current_day - 1):
            rx = int(day_data.find("rx").text)
            tx = int(day_data.find("tx").text)
            break
    
    yesterday = round((rx + tx) / 1024 / 1024 , 2)

    return total, yesterday

def update_yaml_file():
    """更新订阅配置文件"""
    yaml = YAML()
    yaml.preserve_quotes = True
    
    with open('subscribe.yaml', 'r') as f:
        config = yaml.load(f)

    total, today = get_bandwidth_usage()
    now = datetime.now()
    
    # 更新节点名称
    config['proxies'][0]['name'] = f"{now.month}月流量: {total} GB"
    config['proxies'][1]['name'] = f"昨日使用流量: {today} MB"
    config['proxies'][2]['name'] = now.strftime('%Y-%m-%d %H:%M:%S')

    with open('subscribe.yaml', 'w') as f:
        yaml.dump(config, f)

def get_changed_files():
    """获取已修改和新增的文件列表，排除.env和隐藏文件"""
    # 将所有修改添加到暂存区
    subprocess.run(['git', 'add', '-A'], stdout=subprocess.PIPE)
    
    # 获取已暂存文件列表
    result = subprocess.run(['git', 'diff', '--name-only', '--cached'], stdout=subprocess.PIPE)
    return [f for f in result.stdout.decode('utf-8').split('\n') 
            if f and not f.startswith('.') and f != '.env']

def _sync_with_remote(repo_path, branch):
    """同步远程仓库"""
    from git import GitCommandError, Repo
    import logging 
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    try:
        repo = Repo(repo_path)
        remote = repo.remote()
        logger.info(f"正在从 {remote.name}/{branch} 同步代码...")
        remote.pull(branch)
        logger.info("同步完成")
        return True
    except GitCommandError as e:
        logger.error(f"同步失败: {str(e)}")
        return False

def git_upload(commit_message=None):
    """推送更改到GitHub仓库"""
    try:
        # 加载环境变量和认证信息
        token = os.getenv('GITHUB_TOKEN')
        username = os.getenv('GITHUB_USERNAME')
        repo_name = os.getenv('GITHUB_REPO')
        
        if not all([token, username, repo_name]):
            raise ValueError("缺少必要的环境变量配置")

        # 设置默认提交信息
        if not commit_message:
            commit_message = f"update subscription - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # 初始化GitHub客户端
        g = Github(auth=Auth.Token(token))
        user = g.get_user()
        print(f"已认证用户: {user.login}")
        
        # 获取仓库和分支信息
        repo = user.get_repo(repo_name)
        print(f"操作仓库: {repo.full_name}")
        
        default_branch = repo.default_branch
        ref = repo.get_git_ref(f'heads/{default_branch}')
        
        # 获取当前commit和tree
        current_commit = repo.get_commit(ref.object.sha)
        base_tree = current_commit.commit.tree
        print(f"当前commit: {current_commit.sha}")
        
        # 获取已修改文件
        changed_files = get_changed_files()
        if not changed_files:
            print("没有文件需要提交")
            return True
            
        print(f"需要提交的文件: {changed_files}")
        
        # 准备文件更新列表
        element_list = []
        for file_path in changed_files:
            try:
                # 读取文件内容
                with open(file_path, 'rb') as f:
                    content = f.read()

                # 处理文本和二进制文件
                try:
                    # 尝试以UTF-8解码
                    content_str = content.decode('utf-8')
                    blob = repo.create_git_blob(content_str, 'utf-8')
                except UnicodeDecodeError:
                    # 处理二进制文件
                    print(f"文件 {file_path} 为二进制文件，使用base64编码")
                    blob = repo.create_git_blob(base64.b64encode(content).decode('ascii'), 'base64')
                
                # 添加到更新列表
                element_list.append(InputGitTreeElement(
                    path=file_path,
                    mode='100644',  # 常规文件
                    type='blob',
                    sha=blob.sha
                ))
                
            except Exception as e:
                print(f"处理文件 {file_path} 时出错: {str(e)}")
        
        if not element_list:
            print("没有有效文件需要提交")
            return True
            
        # 创建新的tree并提交
        try:
            new_tree = repo.create_git_tree(element_list, base_tree)
            parent = [repo.get_git_commit(ref.object.sha)]
            new_commit = repo.create_git_commit(commit_message, new_tree, parent)
            ref.edit(new_commit.sha)
            
            print(f"成功推送更改到GitHub: {commit_message}")

            # 同步远程仓库
            print("正在同步远程仓库...")
            import time
            time.sleep(2)
            _sync_with_remote('.', default_branch)

            return True
        except Exception as e:
            print(f"创建Git树或提交时出错: {str(e)}")
            return False
        
    except GithubException as e:
        print(f"GitHub API错误: {e.data.get('message', str(e))}")
        return False
    except Exception as e:
        print(f"发生未知错误: {str(e)}")
        return False

if __name__ == '__main__':
    load_dotenv()
    update_yaml_file()    
    git_upload()