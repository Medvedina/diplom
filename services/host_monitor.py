import asyncio
import aiohttp
import socket
import subprocess
from typing import Dict, List
import time

class HostMonitor:
    def __init__(self):
        self.host_status_cache = {}
        self.last_update = {}
    
    async def check_host_status(self, host: str, port: int = 22) -> Dict:
        """Асинхронная проверка статуса хоста"""
        try:
            # Проверка ping
            ping_result = await self._check_ping(host)
            
            if ping_result['status'] == 'up':
                # Проверка SSH
                ssh_result = await self._check_ssh(host, port)
                return {
                    'host': host,
                    'status': 'up' if ssh_result['status'] == 'up' else 'ssh_error',
                    'ping': ping_result,
                    'ssh': ssh_result,
                    'timestamp': time.time()
                }
            else:
                return {
                    'host': host,
                    'status': 'down',
                    'ping': ping_result,
                    'timestamp': time.time()
                }
        except Exception as e:
            return {
                'host': host,
                'status': 'error',
                'error': str(e),
                'timestamp': time.time()
            }
    
    async def check_multiple_hosts(self, hosts: List[str]) -> List[Dict]:
        """Проверка нескольких хостов параллельно"""
        tasks = [self.check_host_status(host) for host in hosts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтруем исключения
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Error checking host: {result}")
            else:
                valid_results.append(result)
        
        # Обновляем кэш
        for result in valid_results:
            self.host_status_cache[result['host']] = result
        
        return valid_results
    
    async def _check_ping(self, host: str) -> Dict:
        """Асинхронный ping"""
        try:
            # Для Linux/Unix
            proc = await asyncio.create_subprocess_exec(
                'ping', '-c', '1', '-W', '2', host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            return {
                'status': 'up' if proc.returncode == 0 else 'down',
                'latency': self._extract_latency(stdout.decode())
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    async def _check_ssh(self, host: str, port: int) -> Dict:
        """Проверка доступности SSH порта"""
        try:
            # Создаем соединение
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=3.0
            )
            
            writer.close()
            await writer.wait_closed()
            
            return {'status': 'up', 'port': port}
        except asyncio.TimeoutError:
            return {'status': 'timeout', 'port': port}
        except ConnectionRefusedError:
            return {'status': 'refused', 'port': port}
        except Exception as e:
            return {'status': 'error', 'error': str(e), 'port': port}
    
    def _extract_latency(self, ping_output: str) -> float:
        """Извлекает время задержки из вывода ping"""
        import re
        pattern = r'time=([\d.]+) ms'
        match = re.search(pattern, ping_output)
        return float(match.group(1)) if match else 0.0
    
    def get_cached_status(self, host: str) -> Dict:
        """Получить кэшированный статус хоста"""
        return self.host_status_cache.get(host, {'status': 'unknown'})

# Синглтон экземпляр
monitor = HostMonitor()

async def check_host_status_async(host: str) -> Dict:
    """Публичная функция для проверки хоста"""
    return await monitor.check_host_status(host)