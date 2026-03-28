#!/usr/bin/env python3
"""
Сборщик метрик разработки из GitHub
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from github import Github, GithubException
import requests

class MetricsCollector:
    def __init__(self, token, repo_name):
        self.github = Github(token)
        self.repo = self.github.get_repo(repo_name)
        self.repo_name = repo_name
        self.metrics = {}
        
    def collect_all_metrics(self):
        """Сбор всех метрик"""
        print("📊 Начинаю сбор метрик...")
        
        self.metrics = {
            "timestamp": datetime.now().isoformat(),
            "repository": self.repo_name,
            "commits": self.get_commit_activity(),
            "code_review": self.get_code_review_metrics(),
            "releases": self.get_release_metrics(),
            "technical_debt": self.get_technical_debt(),
            "pull_requests": self.get_pr_metrics(),
            "issues": self.get_issue_metrics(),
            "contributors": self.get_contributor_stats()
        }
        
        # Сохраняем метрики
        self.save_metrics()
        print("✅ Сбор метрик завершен!")
        
        return self.metrics
    
    def get_commit_activity(self):
        """Активность коммитов"""
        print("  📝 Собираю статистику коммитов...")
        
        # За последние 90 дней
        since_date = datetime.now() - timedelta(days=90)
        
        commits = list(self.repo.get_commits(since=since_date))
        
        # Анализ по дням
        daily_commits = defaultdict(int)
        weekly_commits = defaultdict(int)
        authors = defaultdict(int)
        
        for commit in commits:
            date = commit.commit.author.date.date()
            week = date.isocalendar()[1]
            daily_commits[date.isoformat()] += 1
            weekly_commits[week] += 1
            authors[commit.commit.author.name] += 1
            
        return {
            "total_commits_90d": len(commits),
            "avg_daily": len(commits) / 90,
            "daily": dict(daily_commits),
            "weekly": dict(weekly_commits),
            "top_authors": dict(sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5])
        }
    
    def get_code_review_metrics(self):
        """Метрики Code Review"""
        print("  👀 Собираю метрики Code Review...")
        
        since_date = datetime.now() - timedelta(days=90)
        prs = list(self.repo.get_pulls(state='closed', sort='updated', 
                                        direction='desc'))
        
        review_times = []
        review_comments = defaultdict(int)
        reviewers = defaultdict(int)
        
        for pr in prs[:100]:  # Последние 100 PR
            if pr.created_at > since_date and pr.merged:
                # Время до первого ревью
                reviews = list(pr.get_reviews())
                if reviews:
                    first_review_time = (reviews[0].submitted_at - pr.created_at).total_seconds() / 3600
                    review_times.append(first_review_time)
                    
                # Сбор комментариев
                comments = list(pr.get_issue_comments())
                review_comments[pr.user.login] += len(comments)
                
                for reviewer in set([r.user.login for r in reviews]):
                    reviewers[reviewer] += 1
        
        avg_review_time = sum(review_times) / len(review_times) if review_times else 0
        
        return {
            "avg_review_time_hours": round(avg_review_time, 2),
            "median_review_time_hours": round(sorted(review_times)[len(review_times)//2], 2) if review_times else 0,
            "prs_reviewed": len(review_times),
            "avg_comments_per_pr": sum(review_comments.values()) / len(prs) if prs else 0,
            "top_reviewers": dict(sorted(reviewers.items(), key=lambda x: x[1], reverse=True)[:5])
        }
    
    def get_release_metrics(self):
        """Частота релизов"""
        print("  🚀 Собираю метрики релизов...")
        
        releases = list(self.repo.get_releases())
        
        release_dates = []
        release_names = []
        
        for release in releases:
            if release.published_at:
                release_dates.append(release.published_at)
                release_names.append(release.tag_name)
        
        # Вычисляем частоту
        if len(release_dates) > 1:
            dates_sorted = sorted(release_dates)
            intervals = []
            for i in range(1, len(dates_sorted)):
                interval = (dates_sorted[i] - dates_sorted[i-1]).days
                intervals.append(interval)
            avg_interval = sum(intervals) / len(intervals)
        else:
            avg_interval = 0
            
        return {
            "total_releases": len(releases),
            "releases_last_90d": len([r for r in releases if r.published_at and 
                                      r.published_at > datetime.now() - timedelta(days=90)]),
            "avg_release_interval_days": round(avg_interval, 1),
            "release_frequency": round(len(releases) * 365 / 90, 1) if releases else 0,  # релизов в год
            "latest_release": release_names[0] if release_names else None,
            "release_dates": [d.isoformat() for d in release_dates]
        }
    
    def get_technical_debt(self):
        """Метрики технического долга"""
        print("  💰 Оцениваю технический долг...")
        
        # Открытые issues с метками технического долга
        debt_issues = list(self.repo.get_issues(labels=['technical-debt', 'refactor', 'debt'],
                                                 state='open'))
        
        # Старые PR (более 30 дней)
        old_prs = list(self.repo.get_pulls(state='open'))
        old_prs = [pr for pr in old_prs if (datetime.now() - pr.created_at).days > 30]
        
        # Файлы с TODOs и FIXMEs
        todos = self.count_todos_in_code()
        
        # Code Smells через API (если есть интеграция с SonarQube)
        code_smells = self.get_sonarqube_metrics() if self.check_sonarqube() else None
        
        return {
            "open_debt_issues": len(debt_issues),
            "old_prs_count": len(old_prs),
            "old_prs_avg_age_days": sum([(datetime.now() - pr.created_at).days for pr in old_prs]) / len(old_prs) if old_prs else 0,
            "todos_count": todos['todos'],
            "fixmes_count": todos['fixmes'],
            "code_smells": code_smells,
            "debt_ratio": round(len(debt_issues) / max(self.repo.get_issues(state='all').totalCount, 1) * 100, 1)
        }
    
    def count_todos_in_code(self):
        """Поиск TODO и FIXME в коде"""
        todos = 0
        fixmes = 0
        
        try:
            # Рекурсивно проходим по файлам в репозитории
            contents = self.repo.get_contents("")
            self._scan_directory(contents, todos, fixmes)
        except Exception as e:
            print(f"  ⚠️ Не удалось просканировать файлы: {e}")
            
        return {"todos": todos, "fixmes": fixmes}
    
    def _scan_directory(self, contents, todos, fixmes):
        """Рекурсивное сканирование директорий"""
        for content in contents:
            if content.type == "dir":
                try:
                    sub_contents = self.repo.get_contents(content.path)
                    self._scan_directory(sub_contents, todos, fixmes)
                except:
                    pass
            elif content.type == "file" and content.name.endswith(('.py', '.js', '.ts', '.java', '.go', '.rs')):
                try:
                    file_content = content.decoded_content.decode('utf-8', errors='ignore')
                    todos += file_content.lower().count('todo')
                    fixmes += file_content.lower().count('fixme')
                except:
                    pass
    
    def get_pr_metrics(self):
        """Метрики Pull Requests"""
        print("  🔄 Собираю метрики PR...")
        
        since_date = datetime.now() - timedelta(days=90)
        prs = list(self.repo.get_pulls(state='all', sort='updated'))
        
        merged = [pr for pr in prs if pr.merged and pr.created_at > since_date]
        closed_not_merged = [pr for pr in prs if pr.state == 'closed' and not pr.merged]
        open_prs = [pr for pr in prs if pr.state == 'open']
        
        # Средний размер PR (добавленные строки)
        pr_sizes = []
        for pr in merged[:50]:  # Последние 50
            try:
                files = list(pr.get_files())
                additions = sum(f.additions for f in files)
                pr_sizes.append(additions)
            except:
                pass
        
        return {
            "merged_90d": len(merged),
            "closed_not_merged_90d": len(closed_not_merged),
            "open_prs": len(open_prs),
            "merge_rate": round(len(merged) / max(len(merged) + len(closed_not_merged), 1) * 100, 1),
            "avg_pr_size_lines": round(sum(pr_sizes) / len(pr_sizes), 1) if pr_sizes else 0,
            "prs_with_conflicts": len([pr for pr in merged if pr.mergeable is False])
        }
    
    def get_issue_metrics(self):
        """Метрики Issues"""
        print("  🐛 Собираю метрики Issues...")
        
        since_date = datetime.now() - timedelta(days=90)
        issues = list(self.repo.get_issues(state='all', since=since_date))
        
        # Убираем PR из issues
        issues = [i for i in issues if not i.pull_request]
        
        closed = [i for i in issues if i.state == 'closed']
        open_issues = [i for i in issues if i.state == 'open']
        
        # Время закрытия
        close_times = []
        for issue in closed:
            if issue.closed_at:
                close_time = (issue.closed_at - issue.created_at).days
                close_times.append(close_time)
        
        return {
            "total_issues_90d": len(issues),
            "closed_90d": len(closed),
            "open_issues": len(open_issues),
            "avg_close_time_days": round(sum(close_times) / len(close_times), 1) if close_times else 0,
            "issues_per_contributor": len(issues) / max(self.get_contributor_count(), 1)
        }
    
    def get_contributor_stats(self):
        """Статистика по контрибьюторам"""
        print("  👥 Собираю статистику контрибьюторов...")
        
        contributors = list(self.repo.get_contributors())
        stats = []
        
        for contributor in contributors[:10]:  # Топ-10
            try:
                commits = self.repo.get_commits(author=contributor.login)
                stats.append({
                    "name": contributor.login,
                    "commits": commits.totalCount,
                    "avatar": contributor.avatar_url
                })
            except:
                pass
                
        return {
            "total_contributors": len(contributors),
            "active_contributors_90d": len([c for c in contributors if c.contributions > 0]),
            "top_contributors": stats
        }
    
    def get_contributor_count(self):
        """Получение количества контрибьюторов"""
        try:
            return self.repo.get_contributors().totalCount
        except:
            return 1
    
    def check_sonarqube(self):
        """Проверка наличия SonarQube интеграции"""
        # Здесь можно добавить проверку наличия SonarQube
        return False
    
    def get_sonarqube_metrics(self):
        """Получение метрик из SonarQube (если настроен)"""
        # Здесь добавить интеграцию с SonarQube API
        return None
    
    def save_metrics(self):
        """Сохранение метрик в файлы"""
        os.makedirs('metrics', exist_ok=True)
        os.makedirs('docs/data', exist_ok=True)
        
        # Сохраняем в JSON
        with open('metrics/metrics.json', 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, indent=2, default=str)
            
        # Сохраняем в CSV для аналитики
        self.save_csv_metrics()
        
        # Сохраняем для дашборда
        with open('docs/data/dashboard_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, indent=2, default=str)
            
    def save_csv_metrics(self):
        """Сохранение в CSV формате"""
        # Коммиты по дням
        if self.metrics['commits']['daily']:
            df_commits = pd.DataFrame(
                list(self.metrics['commits']['daily'].items()),
                columns=['date', 'commits']
            )
            df_commits.to_csv('metrics/daily_commits.csv', index=False)
            
        # Метрики для дашборда
        summary = {
            'metric': ['total_commits_90d', 'avg_review_time_hours', 'total_releases', 
                      'open_debt_issues', 'merge_rate', 'avg_close_time_days'],
            'value': [
                self.metrics['commits']['total_commits_90d'],
                self.metrics['code_review']['avg_review_time_hours'],
                self.metrics['releases']['total_releases'],
                self.metrics['technical_debt']['open_debt_issues'],
                self.metrics['pull_requests']['merge_rate'],
                self.metrics['issues']['avg_close_time_days']
            ]
        }
        df_summary = pd.DataFrame(summary)
        df_summary.to_csv('metrics/summary_metrics.csv', index=False)

# Запуск сбора метрик
if __name__ == "__main__":
    token = os.getenv('GITHUB_TOKEN')
    repo_name = os.getenv('GITHUB_REPOSITORY', os.getenv('REPO_NAME'))
    
    if not repo_name:
        print("❌ REPO_NAME не указан!")
        exit(1)
        
    collector = MetricsCollector(token, repo_name)
    collector.collect_all_metrics()
