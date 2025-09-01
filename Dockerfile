FROM apify/actor-python:3.11

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Google Chrome + runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg wget unzip ca-certificates \
    fonts-liberation xdg-utils libnss3 libasound2 libu2f-udev libgbm1 \
    libgtk-3-0 libglib2.0-0 libgdk-pixbuf2.0-0 libdrm2 libxdamage1 libx11-xcb1 libpangocairo-1.0-0 \
 && wget -qO- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-linux.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

# (We rely on Selenium Manager to fetch the correct chromedriver)
ENV CHROME_BIN=/usr/bin/google-chrome

COPY . .

# Use main.py for local development (Apify deployment commented out)
# CMD ["python", "apify_selector.py"]  # Apify-specific - commented out
CMD ["python", "main.py"]