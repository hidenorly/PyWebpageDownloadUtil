#   Copyright 2023 hidenorly
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import os
import re
import random
import requests
import string
import random
import time

from PIL import Image
from io import BytesIO
import cairosvg
import pyheif
import urllib.request
from urllib.parse import urljoin
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


globalCache = {}

class ImageUtil:
    def getFilenameWithExt(filename, ext=".jpeg"):
        filename = os.path.splitext(filename)[0]
        return filename + ext

    def covertToJpeg(imageFile):
        outFilename = ImageUtil.getFilenameWithExt(imageFile, ".jpeg")
        image = None
        if imageFile.endswith(('.heic', '.HEIC')):
            try:
                heifImage = pyheif.read(imageFile)
                image = Image.frombytes(
                    heifImage.mode,
                    heifImage.size,
                    heifImage.data,
                    "raw",
                    heifImage.mode,
                    heifImage.stride,
                )
            except:
                pass
        else:
            try:
                image = Image.open(imageFile)
            except:
                pass
        if image:
            image.save(outFilename, "JPEG")
        return outFilename

    def getImageSize(imageFile):
        try:
            with Image.open(imageFile) as img:
                return img.size
        except:
            return None

    def getImageSizeFromChunk(data):
        try:
            with Image.open(BytesIO(data)) as img:
                return img.size
        except:
            return None

    def convertSvgToPng(svgPath, pngPath, width=1920, height=1080):
        try:
            cairosvg.svg2png(url=svgPath, write_to=pngPath, output_width=width, output_height=height)
        except:
            pass



class WebPageImageDownloader:
    def __init__(self, width=1920, height=1080):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        tempDriver = webdriver.Chrome(options=options)
        userAgent = tempDriver.execute_script("return navigator.userAgent")
        userAgent = userAgent.replace("headless", "")
        userAgent = userAgent.replace("Headless", "")

        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument(f"user-agent={userAgent}")
        driver = webdriver.Chrome(options=options)
        driver.set_window_size(width, height)
        self.driver = driver
        self._driver = tempDriver

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
        if self._driver:
            self._driver.close()
            self._driver = None

    def getRandomFilename(self):
        letters = string.ascii_lowercase
        return ''.join(random.choice(letters) for i in range(10))

    def getSanitizedFilenameFromUrl(self, url):
        parsed_url = urllib.parse.urlparse(url)
        filename = parsed_url.path.split('/')[-1]

        filename = re.sub(r'[\\/:*?"<>|]', '', filename)

        return filename

    def getOutputFileStream(self, outputPath, url):
        f = None
        filename = self.getSanitizedFilenameFromUrl(url)
        filename = str(os.path.join(outputPath, filename))
        if not filename.endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif')):
            filename = filename+".jpeg"

        try:
            f = open(filename, 'wb')
        except:
            filename = os.path.join(outputPath, self.getRandomFilename())
            f = open(filename, 'wb')
        filePath = filename
        filename = os.path.basename(filename)
        return f, filename, filePath


    def downloadImage(self, imageUrl, outputPath, minDownloadSize=None):
        filename = None
        url = None
        if not imageUrl in globalCache:
            globalCache[imageUrl] = True
            filePath = None

            if imageUrl.strip().endswith((".heic", ".HEIC", ".svg")):
                try:
                    with urllib.request.urlopen(imageUrl) as response:
                        imgContent = response.read()
                        url =imageUrl
                        f, filename, filePath = self.getOutputFileStream(outputPath, imageUrl)
                        if f:
                            f.write(imgContent)
                            f.close()
                except:
                    pass

                if os.path.exists(filePath):
                    if imageUrl.strip().endswith((".svg")):
                        newPngPath = filePath+".png"
                        ImageUtil.convertSvgToPng(filePath, newPngPath)
                        if os.path.exists(newPngPath):
                            filename = newPngPath
                    else:
                        # .heic, .HEIC
                        newJpegPath = ImageUtil.covertToJpeg(filePath)
                        if os.path.exists(newJpegPath):
                            size = ImageUtil.getImageSize(newJpegPath)
                            if minDownloadSize==None or (size and size[0] >= minDownloadSize[0] and size[1] >= minDownloadSize[1]):
                                filename = newJpegPath
            else:
                # .png, .jpeg, etc.
                size = None
                response = None
                try:
                    response = requests.get(imageUrl)
                    if response.status_code == 200:
                        # check image size
                        size = ImageUtil.getImageSizeFromChunk(response.content)
                except:
                    pass

                if response:
                    if minDownloadSize==None or (size and size[0] >= minDownloadSize[0] and size[1] >= minDownloadSize[1]):
                        url =imageUrl
                        f, filename, filePath = self.getOutputFileStream(outputPath, imageUrl)
                        if f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                            f.close()

        return filename, url

    def isSameDomain(self, url1, url2, baseUrl=""):
        isSame = urlparse(url1).netloc == urlparse(url2).netloc
        isbaseUrl =  ( (baseUrl=="") or url2.startswith(baseUrl) )
        return isSame and isbaseUrl

    def _downloadImagesFromWebPage(self, fileUrls, pageUrls, pageUrl, outputPath, minDownloadSize, baseUrl, maxDepth, depth, usePageUrl, timeOut):
        driver = self.driver

        if driver==None or depth > maxDepth:
            return

        element = None
        try:
            if not pageUrl in globalCache:
                #globalCache[pageUrl] = True
                driver.get(pageUrl)
                element = WebDriverWait(driver, timeOut).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'a'))
                )
                element = WebDriverWait(driver, timeOut).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'img'))
                )
        except:
            pass

        if element:
            # download image
            for img_tag in driver.find_elements(By.TAG_NAME, 'img'):
                imageUrl = None
                try:
                    imageUrl = img_tag.get_attribute('src')
                except:
                    pass
                if imageUrl:
                    imageUrl = urljoin(pageUrl, imageUrl)
                    fileName, url = self.downloadImage(imageUrl, outputPath, minDownloadSize)
                    if fileName and not fileName in fileUrls:
                        if usePageUrl:
                            fileUrls[fileName] = pageUrl
                        elif url:
                            fileUrls[fileName] = url

            # get links to other pages
            links = driver.find_elements(By.TAG_NAME, 'a')
            for link in links:
                if link:
                    href = None
                    try:
                        href = link.get_attribute('href')
                    except:
                        continue #print("Error occured (href is not found in a tag) at "+str(link))
                    if href and self.isSameDomain(pageUrl, href, baseUrl):
                        if not href in pageUrls:
                            pageUrls.add(href)
                            if href.endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif')):
                                fileName, url = self.downloadImage(href, outputPath, minDownloadSize)
                                if fileName and not fileName in fileUrls:
                                    if usePageUrl:
                                        fileUrls[fileName] = pageUrl
                                    elif url:
                                        fileUrls[fileName] = url
                            else:
                                self._downloadImagesFromWebPage(fileUrls, pageUrls, href, outputPath, minDownloadSize, baseUrl, maxDepth, depth + 1, usePageUrl, timeOut)




    def downloadImagesFromWebPages(self, urls, outputPath, minDownloadSize=None, baseUrl="", maxDepth=1, usePageUrl=False, timeOut=60):
        fileUrls = {}

        driver = self.driver

        pageUrls=set()
        for url in urls:
            self._downloadImagesFromWebPage(fileUrls, pageUrls, url, outputPath, minDownloadSize, baseUrl, maxDepth, 0, usePageUrl, timeOut)

        return fileUrls
