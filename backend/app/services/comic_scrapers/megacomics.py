"""
MegaComicsTV3 Scraper
Scrapes comics from megacomicstv3.blogspot.com
"""

import aiohttp
import asyncio
import re
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

from app.services.comic_scrapers.base import (
    ComicScraperBase, 
    ScraperResult, 
    DownloadLink,
    HostType
)

logger = logging.getLogger(__name__)


class MegaComicsScraper(ComicScraperBase):
    """
    Scraper for MegaComicsTV3 (megacomicstv3.blogspot.com)
    
    Features:
    - Spanish comics (Marvel, DC, Indies)
    - CBR format
    - Mega and Mediafire links
    """
    
    name = "megacomics"
    base_url = "https://megacomicstv3.blogspot.com"
    
    async def search(self, query: str, page: int = 1) -> List[Dict]:
        """
        Search for comics on MegaComicsTV3
        
        Uses Blogger's search functionality
        """
        results = []
        
        try:
            # Blogger search URL
            search_url = f"{self.base_url}/search?q={quote(query)}"
            if page > 1:
                # Blogger pagination uses start parameter
                start = (page - 1) * 20
                search_url += f"&start={start}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    search_url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Search failed: HTTP {response.status}")
                        return []
                    
                    html = await response.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find comic entries (Blogger post format)
            # Looking for article or post containers
            posts = soup.select('article, .post, .hentry, .Blog1 .post-outer')
            
            for post in posts:
                try:
                    # Get title and link
                    title_elem = post.select_one('h2 a, h3 a, .post-title a, .entry-title a')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    
                    if not url:
                        continue
                    
                    # Get cover image
                    img_elem = post.select_one('img')
                    cover = img_elem.get('src', '') if img_elem else None
                    
                    # Parse title for issue info
                    # Format: "Comic Name [X/Y] [Español] [Mega - Mediafire]"
                    issues_match = re.search(r'\[(\d+)/(\d+\??)\]', title)
                    issues = f"{issues_match.group(1)}/{issues_match.group(2)}" if issues_match else None
                    
                    # Clean title (remove brackets info)
                    clean_title = re.sub(r'\s*\[.*?\]', '', title).strip()
                    
                    results.append({
                        'title': clean_title,
                        'full_title': title,
                        'url': url,
                        'cover': cover,
                        'issues': issues,
                        'source': self.name
                    })
                    
                except Exception as e:
                    logger.warning(f"Error parsing post: {e}")
                    continue
            
            logger.info(f"MegaComics search '{query}': found {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"MegaComics search error: {e}")
            return []
    
    async def get_download_links(self, url: str) -> ScraperResult:
        """
        Extract download links from a comic page
        
        MegaComicsTV3 typically has:
        - Direct Mega/Mediafire links
        - Sometimes behind shorteners (ouo.io, etc.)
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        return ScraperResult(
                            title="Unknown",
                            source=self.name,
                            source_url=url,
                            success=False,
                            error=f"HTTP {response.status}"
                        )
                    
                    html = await response.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Get title
            title_elem = soup.select_one('h1, .post-title, .entry-title')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            
            # Clean title
            clean_title = re.sub(r'\s*\[.*?\]', '', title).strip()
            
            # Get description
            desc_elem = soup.select_one('.post-body, .entry-content')
            description = None
            if desc_elem:
                # Get first paragraph as description
                first_p = desc_elem.select_one('p')
                if first_p:
                    description = first_p.get_text(strip=True)[:500]
            
            # Get cover image
            cover = None
            img_elem = soup.select_one('.post-body img, .entry-content img')
            if img_elem:
                cover = img_elem.get('src', '')
            
            # Extract file info
            file_size = None
            year = None
            
            # Look for "Tamaño : XXX MB" pattern
            size_match = re.search(r'Tamaño\s*:\s*([\d.,]+\s*[GMK]?B)', html, re.IGNORECASE)
            if size_match:
                file_size = size_match.group(1)
            
            # Look for year
            year_match = re.search(r'Año\s*:\s*(\d{4})', html, re.IGNORECASE)
            if year_match:
                year = int(year_match.group(1))
            
            # Extract download links
            download_links = []
            
            # Method 1: Look for direct Mega/Mediafire links
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                
                # Skip non-download links
                if not href or href.startswith('#') or 'javascript:' in href:
                    continue
                
                # Check if it's a download host
                host = self.detect_host(href)
                
                if host in [HostType.MEGA, HostType.MEDIAFIRE, HostType.GOOGLE_DRIVE, HostType.TERABOX]:
                    # Check if already added (avoid duplicates)
                    if not any(dl.url == href for dl in download_links):
                        download_links.append(self.create_download_link(href, file_size))
                        logger.info(f"Found {host.value} link: {href[:50]}...")
            
            # Method 2: Look for links in onclick attributes or data attributes
            for elem in soup.find_all(attrs={'onclick': True}):
                onclick = elem.get('onclick', '')
                urls = re.findall(r"(?:window\.open|location\.href)\s*[=\(]\s*['\"]([^'\"]+)['\"]", onclick)
                for found_url in urls:
                    host = self.detect_host(found_url)
                    if host != HostType.UNKNOWN and not any(dl.url == found_url for dl in download_links):
                        download_links.append(self.create_download_link(found_url, file_size))
            
            # Method 3: Look for encoded/hidden links in scripts
            scripts = soup.find_all('script')
            for script in scripts:
                script_text = script.string or ''
                # Look for Mega links
                mega_matches = re.findall(r'https?://mega\.(?:nz|co\.nz)/[^\s"\'<>]+', script_text)
                for mega_url in mega_matches:
                    if not any(dl.url == mega_url for dl in download_links):
                        download_links.append(self.create_download_link(mega_url, file_size))
                
                # Look for Mediafire links
                mf_matches = re.findall(r'https?://(?:www\.)?mediafire\.com/[^\s"\'<>]+', script_text)
                for mf_url in mf_matches:
                    if not any(dl.url == mf_url for dl in download_links):
                        download_links.append(self.create_download_link(mf_url, file_size))
            
            # Parse issues from title
            issues_match = re.search(r'\[(\d+)/(\d+\??)\]', title)
            issues = f"{issues_match.group(1)}/{issues_match.group(2)}" if issues_match else None
            
            result = ScraperResult(
                title=clean_title,
                source=self.name,
                source_url=url,
                issues=issues,
                language="es",
                format="cbr",
                download_links=download_links,
                description=description,
                cover_image=cover,
                file_size=file_size,
                year=year,
                success=len(download_links) > 0,
                error=None if download_links else "No download links found"
            )
            
            logger.info(f"MegaComics scraped '{clean_title}': {len(download_links)} links found")
            return result
            
        except Exception as e:
            logger.error(f"MegaComics scrape error: {e}")
            return ScraperResult(
                title="Unknown",
                source=self.name,
                source_url=url,
                success=False,
                error=str(e)
            )
    
    def _get_headers(self) -> dict:
        """Get request headers"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Referer': self.base_url,
        }
