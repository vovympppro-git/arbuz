#!/usr/bin/env python3
"""
Сборщик метрик разработки из GitHub
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from github import Github, Auth
import requests

class MetricsCollector:
    def __init__(self, token, repo_name):
        # Исправленный способ аутентификации
        auth = Auth.Token(token)
        self.github = Github(auth=auth)
        self.repo = self.github.get_repo(repo_name)
        self.repo_name = repo_name
        self.metrics = {}
        
    def collect_all_metrics(self):
        """Сбор всех метрик"""
        print("📊 Начинаю сбор метрик...")
        
        self.metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        since_date = datetime.now(timezone.utc) - timedelta(days=90)
        
        commits = list(self.repo.get_commits(since=since_date))
        
        # Анализ по дням
        daily_commits = defaultdict(int)
        weekly_commits = defaultdict(int)
        authors = defaultdict(int)
        
        for commit in commits:
            # Исправляем проблему с часовыми поясами
            date = commit.commit.author.date.astimezone(timezone.utc).date()
            week = date.isocalendar()[1]
            daily_commits[date.isoformat()] += 1
            weekly_commits[week] += 1
            authors[commit.commit.author.name] += 1
            
        return {
            "total_commits_90d": len(commits),
            "avg_daily": round(len(commits) / 90, 2) if commits else 0,
            "daily": dict(daily_commits),
            "weekly": dict(weekly_commits),
            "top_authors": dict(sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5])
        }
    
    def get_code_review_metrics(self):
        """Метрики Code Review"""
        print("  👀 Собираю метрики Code Review...")
        
        since_date = datetime.now(timezone.utc) - timedelta(days=90)
        prs = list(self.repo.get_pulls(state='closed', sort='updated', 
                                        direction='desc'))
        
        review_times = []
        review_comments = defaultdict(int)
        reviewers = defaultdict(int)
        
        for pr in prs[:100]:  # Последние 100 PR
            # Исправляем сравнение дат
            pr_created = pr.created_at.astimezone(timezone.utc)
            
            if pr_created > since_date and pr.merged:
                # Время до первого ревью
                reviews = list(pr.get_reviews())
                if reviews:
                    review_time = reviews[0].submitted_at.astimezone(timezone.utc)
                    first_review_time = (review_time - pr_created).total_seconds() / 3600
                    review_times.append(first_review_time)
                    
                # Сбор комментариев
                comments = list(pr.get_issue_comments())
                review_comments[pr.user.login] += len(comments)
                
                for reviewer in set([r.user.login for r in reviews if r.user]):
                    reviewers[reviewer] += 1
        
        avg_review_time = sum(review_times) / len(review_times) if review_times else 0
        median_review_time = sorted(review_times)[len(review_times)//2] if review_times else 0
        
        return {
            "avg_review_time_hours": round(avg_review_time, 2),
            "median_review_time_hours": round(median_review_time, 2),
            "prs_reviewed": len(review_times),
            "avg_comments_per_pr": round(sum(review_comments.values()) / max(len(prs), 1), 2),
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
                release_dates.append(release.published_at.astimezone(timezone.utc))
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
        
        # Релизы за последние 90 дней
        since_date = datetime.now(timezone.utc) - timedelta(days=90)
        releases_last_90d = len([r for r in release_dates if r > since_date])
            
        return {
            "total_releases": len(releases),
            "releases_last_90d": releases_last_90d,
            "avg_release_interval_days": round(avg_interval, 1),
            "release_frequency": round(len(releases) * 365 / 90, 1) if releases else 0,
            "latest_release": release_names[0] if release_names else None,
            "release_dates": [d.isoformat() for d in release_dates]
        }
    
    def get_technical_debt(self):
        """Метрики технического долга"""
        print("  💰 Оцениваю технический долг...")
        
        # Открытые issues с метками технического долга
        try:
            debt_issues = list(self.repo.get_issues(labels=['technical-debt', 'refactor', 'debt'],
                                                     state='open'))
        except:
            debt_issues = []
        
        # Старые PR (более 30 дней) — ИСПРАВЛЕНА ОШИБКА
        open_prs = list(self.repo.get_pulls(state='open'))
        now_utc = datetime.now(timezone.utc)
        old_prs = []
        
        for pr in open_prs:
            pr_created = pr.created_at.astimezone(timezone.utc)
            days_old = (now_utc - pr_created).days
            if days_old > 30:
                old_prs.append(pr)
        
        # Подсчет TODOs (упрощенная версия, чтобы избежать рекурсии)
        todos_count = 0
        fixmes_count = 0
        
        try:
            # Пытаемся найти TODO только в корневых файлах
            contents = self.repo.get_contents("")
            for content in contents:
                if content.type == "file" and content.name.endswith(('.py', '.js', '.ts', '.java', '.go', '.rs')):
                    try:
                        file_content = content.decoded_content.decode('utf-8', errors='ignore')
                        todos_count += file_content.lower().count('todo')
                        fixmes_count += file_content.lower().count('fixme')
                    except:
                        pass
        except Exception as e:
            print(f"  ⚠️ Не удалось просканировать файлы: {e}")
        
        return {
            "open_debt_issues": len(debt_issues),
            "old_prs_count": len(old_prs),
            "old_prs_avg_age_days": round(sum([(now_utc - pr.created_at.astimezone(timezone.utc)).days for pr in old_prs]) / max(len(old_prs), 1), 1),
            "todos_count": todos_count,
            "fixmes_count": fixmes_count,
            "debt_ratio": round(len(debt_issues) / max(self.repo.get_issues(state='all').totalCount, 1) * 100, 1)
        }
    
    def get_pr_metrics(self):
        """Метрики Pull Requests"""
        print("  🔄 Собираю метрики PR...")
        
        since_date = datetime.now(timezone.utc) - timedelta(days=90)
        all_prs = list(self.repo.get_pulls(state='all', sort='updated'))
        
        merged = []
        closed_not_merged = []
        open_prs = []
        
        for pr in all_prs:
            pr_created = pr.created_at.astimezone(timezone.utc)
            if pr_created < since_date:
                continue
                
            if pr.merged:
                merged.append(pr)
            elif pr.state == 'closed':
                closed_not_merged.append(pr)
            elif pr.state == 'open':
                open_prs.append(pr)
        
        # Средний размер PR (добавленные строки)
        pr_sizes = []
        for pr in merged[:50]:  # Последние 50
            try:
                files = list(pr.get_files())
                additions = sum(f.additions for f in files)
                pr_sizes.append(additions)
            except:
                pass
        
        merge_rate = round(len(merged) / max(len(merged) + len(closed_not_merged), 1) * 100, 1)
        
        return {
            "merged_90d": len(merged),
            "closed_not_merged_90d": len(closed_not_merged),
            "open_prs": len(open_prs),
            "merge_rate": merge_rate,
            "avg_pr_size_lines": round(sum(pr_sizes) / max(len(pr_sizes), 1), 1),
            "prs_with_conflicts": len([pr for pr in merged if pr.mergeable is False])
        }
    
    def get_issue_metrics(self):
        """Метрики Issues"""
        print("  🐛 Собираю метрики Issues...")
        
        since_date = datetime.now(timezone.utc) - timedelta(days=90)
        all_issues = list(self.repo.get_issues(state='all', since=since_date))
        
        # Убираем PR из issues
        issues = [i for i in all_issues if not i.pull_request]
        
        closed = [i for i in issues if i.state == 'closed']
        open_issues = [i for i in issues if i.state == 'open']
        
        # Время закрытия
        close_times = []
        for issue in closed:
            if issue.closed_at:
                created = issue.created_at.astimezone(timezone.utc)
                closed_at = issue.closed_at.astimezone(timezone.utc)
                close_time = (closed_at - created).days
                close_times.append(close_time)
        
        return {
            "total_issues_90d": len(issues),
            "closed_90d": len(closed),
            "open_issues": len(open_issues),
            "avg_close_time_days": round(sum(close_times) / max(len(close_times), 1), 1),
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
    
    def save_metrics(self):
        """Сохранение метрик в файлы"""
        os.makedirs('metrics', exist_ok=True)
        os.makedirs('docs/data', exist_ok=True)
        
        # Сохраняем в JSON
        with open('metrics/metrics.json', 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, indent=2, default=str)
            
        # Сохраняем для дашборда
        with open('docs/data/dashboard_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, indent=2, default=str)
            
        # Сохраняем в CSV для аналитики
        self.save_csv_metrics()
            
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
    repo_name = os.getenv('REPO_NAME')
    
    if not repo_name:
        # Если REPO_NAME не задан, пытаемся получить из GITHUB_REPOSITORY
        repo_name = os.getenv('GITHUB_REPOSITORY')
    
    if not repo_name:
        print("❌ REPO_NAME не указан!")
        print("Установите переменную окружения REPO_NAME или GITHUB_REPOSITORY")
        exit(1)
        
    print(f"📂 Репозиторий: {repo_name}")
    collector = MetricsCollector(token, repo_name)
    collector.collect_all_metrics()
