# IT-Linux app

IT-Linux — Django-приложение для ведения личного дневника с ролями автора и модератора, отложенной публикацией, поиском, адаптивными изображениями и инфраструктурой для production-развёртывания.

## В данном проекте реализовано

- регистрация пользователя с подтверждением email;
- вход, выход, редактирование профиля и смена аватара;
- создание, редактирование и удаление собственных статей;
- сохранение статьи в черновик;
- явная отправка статьи на модерацию кнопкой «Опубликовать»;
- публикация и отклонение статьи модератором;
- публичный список и детальная страница статьи;
- поиск по заголовку и содержимому;
- категории статей;
- форма обратной связи;
- Redis-кэширование страниц для анонимных пользователей;
- адаптивные WEBP-изображения для:
  - превью статьи;
  - изображений категорий;
  - изображений, загруженных через TinyMCE;
  - пользовательских аватаров;
- Docker-окружение для production;
- CI workflow для автоматической проверки тестов.

## Роли и сценарии работы

### Автор

Автор может:

- создавать статьи;
- сохранять их как черновики;
- редактировать только свои материалы;
- отправлять черновик на модерацию;
- видеть свои опубликованные статьи, черновики и статьи на проверке.

Статусы для автора работают так:

- черновик: `is_published=False`, `is_approved=False`;
- на модерации: `is_published=True`, `is_approved=False`;
- опубликовано: `is_published=True`, `is_approved=True`.

### Модератор

Модератор не создаёт статьи. Его задача — работать только с очередью модерации:

- просматривать статьи, отправленные авторами на проверку;
- одобрять публикацию;
- отклонять материал.

После изменений модератору недоступно создание статьи ни через интерфейс, ни через URL формы создания.

### Администратор

Администратор имеет полный доступ: может управлять пользователями, публикациями и при необходимости создавать статьи.

## Как взаимодействуют основные части проекта

### Модерация

1. Автор создаёт запись.
2. При обычном сохранении запись остаётся черновиком.
3. При нажатии «Опубликовать» статья не публикуется сразу, а уходит на модерацию.
4. Модератор видит такую запись в профиле в блоке очереди.
5. При одобрении статья становится публичной.
6. При отклонении статья возвращается в состояние черновика.

### Поиск и права доступа

- Анонимный пользователь видит только одобренные и опубликованные записи.
- Автор дополнительно видит свои собственные черновики и материалы на модерации.
- Модератор видит все материалы для проверки.
- Поиск использует те же ограничения доступа, что и список статей, поэтому черновики не утекают в публичную выдачу.

### Изображения

При загрузке изображения проект создаёт адаптивные WEBP-версии для desktop, tablet и mobile. Это применяется к нескольким зонам:

- превью публикации;
- изображению категории;
- изображениям в теле статьи из TinyMCE;
- аватару пользователя.

В шаблонах используются теги и фильтры, которые подставляют `picture/source`, чтобы браузер получал подходящий вариант файла.

### Кэширование

Для анонимных пользователей кэшируются основные публичные страницы. Это снижает нагрузку на БД и ускоряет выдачу. Для авторизованных пользователей кэширование страниц не применяется, чтобы они всегда видели актуальное состояние своих материалов и очереди модерации.

## Технологический стек

- Python 3.13;
- Django 6;
- PostgreSQL;
- Redis;
- TinyMCE;
- Pillow;
- Bootstrap 5;
- Gunicorn;
- Nginx;
- Docker Compose;
- GitHub Actions.

## Переменные окружения

Пример переменных находится в [env.example](env.example).

Основные переменные:

- `SECRET_KEY` — секретный ключ Django;
- `DEBUG` — режим отладки;
- `ALLOWED_HOSTS` — список доменов через запятую;
- `NAME_DB`, `USER_DB`, `PASSWORD_DB`, `HOST_DB`, `PORT_DB` — подключение к PostgreSQL;
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` — Redis;
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` — email;
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` — данные для команды создания администратора;
- `TIME_ZONE` — часовой пояс проекта.

См. [env.example](env.example)

## Локальный запуск без Docker

1. Скопируйте [env.example](env.example) в `.env`.
2. Заполните переменные окружения.
3. Установите зависимости:

   `pip install -r requirements.txt`

4. Примените миграции:

   `python manage.py migrate`

5. При необходимости создайте администратора:

   `python manage.py csu`

6. Запустите сервер разработки:

   `python manage.py runserver`

## Production-запуск через Docker Compose

Production-конфигурация описана в [docker-compose.yml](docker-compose.yml).

Состав сервисов:

- `web` — Django + Gunicorn;
- `nginx` — раздача статики, медиа и reverse proxy;
- `db` — PostgreSQL;
- `redis` — кэш и сессии.

### Шаги запуска

1. Подготовьте `.env` на основе [env.example](env.example).
2. Укажите production-значения для `DEBUG=False`, `ALLOWED_HOSTS` и почтовых настроек.
3. Соберите и запустите сервисы:

   `docker compose up -d --build`

4. После старта приложение будет доступно на 80 порту хоста.

### Что делает контейнер приложения

При запуске `web`-сервис автоматически:

1. применяет миграции;
2. собирает статические файлы в `staticfiles`;
3. создаёт или обновляет администратора командой `csu`;
4. создаёт группу модераторов командой `create_moderators`;
5. загружает тестовый контент пользователей через `add_users_content`;
6. запускает Gunicorn.

Nginx раздаёт содержимое томов со статикой и медиа, а все динамические запросы проксирует в Django.

### Автозаполнение контентом в Docker

В текущей конфигурации [docker-compose.yml](docker-compose.yml) контейнер `web` при старте не только поднимает приложение, но и автоматически выполняет подготовку данных:

- `python manage.py csu --noinput`
- `python manage.py create_moderators --noinput`
- `python manage.py add_users_content --noinput`

Это удобно для быстрого развёртывания демонстрационного окружения с уже подготовленными пользователями и контентом.

Если нужно вручную загрузить данные вне Docker, можно выполнить эти команды отдельно.

## CI

Workflow находится в [.github/workflows/ci.yml](.github/workflows/ci.yml).

Он автоматически:

- поднимает PostgreSQL и Redis;
- устанавливает зависимости;
- запускает Django-тесты.

## Полезные management-команды

- `python manage.py csu` — создать или обновить администратора из переменных окружения;
- `python manage.py create_moderators` — создать группу модераторов и выдать права на модерацию;
- `python manage.py add_users_content` — загрузить фикстуру с пользователями, категориями и их статьями;
- `python manage.py delete_db` — очистить базу данных через `flush`;
- `python manage.py test` — запустить тесты.

## Что ещё важно

- страницы для анонимных пользователей кэшируются через Redis;
- тесты очищают кэш перед сценариями, чтобы результаты были изолированы;
- адаптивные изображения создаются на уровне моделей, а не через сигналы, чтобы логика была сосредоточена в одном месте и проще тестировалась.

# Docker
Установка на Debian:
```angular2html
sudo apt update

sudo apt install ca-certificates curl gnupg
```
```angular2html
sudo install -m 0755 -d /etc/apt/keyrings

curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

sudo chmod a+r /etc/apt/keyrings/docker.gpg


echo \

  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \

  bookworm stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null



```
Установка прав доступа для Docker в Linux, чтобы использовать команды без sudo.
Добавьте пользователя в группу docker, это позволит управлять контейнерами, 
образами и томами без повышения привилегий до root. 


```angular2html
sudo apt update

sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```
Создайте группу docker (если она не создана):
```angular2html
sudo groupadd docker
```
Добавьте вашего пользователя в группу:

```angular2html
sudo usermod -aG docker $USER
```
Примените изменения:
```angular2html
newgrp docker
```
Проверка без sudo:
```angular2html
docker run hello-world
```
Добавление пользователя в группу docker эквивалентно предоставлению прав root,
так как позволяет контейнерам получить доступ к файловой системе хоста.

## Клонирование и развертывание проекта на локальном ПК
Создайте и перейдите в папку:
```angular2html
sudo mkdir /var/www/
cd /var/www/
```
Дайте права на чтение и запись
```
sudo chown -R $USER:$USER /var/www/
sudo chmod -R 755 /var/www/
```

В терминале введите команду для клонирования проекта находясь в папке /var/www
```angular2html
git clone https://github.com/BatiaForWorld/exam.git
```
Перейдите внутрь папки скаченного проекта:
```angular2html
cd /var/www/exam
```
Передзапуском контенеров отключите локальную работу сервисов
```angular2html
sudo systemctl stop postgresql
sudo systemctl stop redis-server
```
Проверьте что они остановлены
```angular2html
sudo systemctl status postgresql
sudo systemctl status redis-server
```
## Docker Compose

### Быстрый запуск

1) Скопируйте шаблон окружения и заполните значения находясь в дериктории проекта:

```bash
cp env.example .env
nano .env
```
Сохраните файл Ctrl+O Enterи выйдите Ctrl+X

2) Запуск всех сервисов одной командой:

```bash
docker compose up --build -d
```
Проверьте в соседнем терминале:
Проверяем Time Zone:
```
docker compose exec web env | grep TIME_ZONE
```
Проверить, какие значения берёт compose для PostgreSQL:

```
docker compose config | grep -A3 POSTGRES_
```
Проверить, какие значения берёт compose для Redis:

```angular2html
docker compose config | grep -A3 REDIS_
```
Миграции применяются автоматически при старте сервиса `web`.

Если нужно пересобрать заново контейнеры, выполните команду:
```angular2html
docker compose down -v
```
И соберите заново:
```angular2html
docker compose up --build -d
```
Если нужно удалить контейнеры и созданную папку с приложение, выполните команду
```angular2html
cd /var/www/exam
docker compose down
cd /var/www/
sudo rm -r exam
cd
```

### Проверка работоспособности на локальном ПК

- Django открыть 
```
http://localhost/
 ```
- PostgreSQL: 
```
docker compose exec db pg_isready -U <USER> -d <NAME>
```
- Redis: 
```
docker compose exec redis redis-cli ping
```


# CI/CD и GitHub Actions

Создайте свой VPS на сервере. 

Это может быть ваш выделенный компьютер для функций сервера или арендованный VPS у хостинг провайдера.

Для своего VPS настройте сеть для доступа ваших контейнеров к глобальной сети интернет, 
открыв порт на роутере 80/tcp
и 22/tcp для удаленного соединения по ssh. 

И внесите настройки ssh после обмена ключами 
с вашим VPS. Advanced --> NAT Forwarding --> Virtual Server

Создайте SSH ключ 
```angular2html
ssh-keygen -t ed25519 -C "email"
```
Добавьте его на ваш VPS:
```angular2html
ssh-copy-id -p 22 user@192.12ваш_ip
```
Напиши YES и введите пароль пользователя под которым вы заходите

Далее войдите в ваш VPS:
```angular2html
ssh -p 22 user@192.12ваш_ip
```

!!!Смените порт ssh по умолчанию.
Откройте файл:
```angular2html
sudo nano /etc/ssh/sshd_config
```
Найдите и измените следующие параметры (уберите #, если строка закомментирована):
- Port 22  `смените на любой выбрав в диапозоне 50000–65000`
- PasswordAuthentication no — запрещает вход по обычному паролю.
- PubkeyAuthentication yes — разрешает вход по ключам.
- PermitRootLogin prohibit-password — (рекомендуется) разрешает root-вход только по ключу.

Сохраните файл `` Ctrl+O`` `` Enter ``и выйдите ``Ctrl+X``
Чтобы настройки вступили в силу перезапустите ssh сервер:
```
sudo systemctl restart ssh
```


Если вы используете LXC контейнеры, то необходимо создать мост, что бы контейнеры могли получали адрес от 
роутера, предварительно зафиксировав MAC адрес LXC контейнера и зарезервировать его в настройках роутера 
**Advanced --> Network --> Lan Settings --> Address Reservation**,
что бы при перезагрузке сервера ваш контейнер не потерял свой ip адрес в локальной сети. 

Установите UFW(Uncomplicated Firewall) — это простой инструмент командной строки для управления 
брандмауэром (firewall) в Linux  
```angular2html
sudo apt update
sudo apt install ufw
```
Откройте порты для доступа сетевого трафика:

Добавьте правила:

Для Nginx

```angular2html
sudo ufw allow 80/tcp
```
Для SSH соединения:
```angular2html
sudo ufw allow 22
```
Если нужно закрыть порт нйдите его порядковый номер командой
```angular2html
sudo ufw status numbered
```
И удалите указав порядковый номер из списка открытых портов
```angular2html
sudo ufw delete 1
```
Не забывайте, что на арендованных VPS так же есть страница настройки правил Firewall.



### Создайте папку для проекта в вашем VPS сервере

```angular2html
sudo mkdir /var/www/it-linux
```
Заполните файл .env по шаблону из env.example
```angular2html
sudo nano /var/www/it-linux/.env
```
Сохраните файл `` Ctrl+O`` `` Enter ``и выйдите ``Ctrl+X``
Посмотрите файл .env, что бы убедиться что он создан
```angular2html
cat /var/www/it-linux/.env
```
Задайте права доступа для группы Docker

Дайте права на чтение и записи в папку проекта с контенерами Docker
```
sudo chown -R $USER:$USER /var/www/it-linux
sudo chmod -R 755 /var/www/it-linux
```
### Добавьте необходимые секреты для GitHub workflows:

DEPLOY_DIR - папка которая содержит проект
```angular2html
/var/www/it-linux
```

DOCKER_HUB_ACCESS_TOKEN - токен с Docker Hub

DOCKER_HUB_USERNAME - логин с Docker Hub

SERVER_IP - ваш публичный IP
	
SSH_KEY - ssh ключ 

Откройте и скопируйте с дефисами c вашего пк, с которого вы обменивались ключами с VPS
```angular2html
cat ~/.ssh/id_ed25519
```
SSH_PORT - порт вашего ssh

SSH_USER - имя пользователя вашего VPS

Выполните push из ветки и автоматически запуститься  action на GitHub.

Дождитесь выполнения workflows. 

### lint. . .  -->

### test. . .  -->

### build. . .  -->

### deploy. . .  !

По завершению успешного deploy приложение будет доступно по адресу

```angular2html
http://it-linux.co
```

Для работы с сервисом воспользуйтесь раннее описанной инструкцией к "Django REST Framework".

## Проверки работы Docker на VPS

Перейдите в папку с проектом в терминале вашего VPS
```angular2html
cd /var/www/it-linux
```

Проверьте работу контейнеров

```angular2html
docker ps
```
Проверьте расход ресурсов вашйей VPS

```angular2html
docker stats
```

### Найдите нужный вам контейнер

Посмотреть контейнер по имени:
```angular2html
docker compose ps
```
Посмотреть контейнер по id:
```angular2html
docker ps
```
Перезапуск выбранного контейнера 
```angular2html
docker restart <id_контейнера или имя_контейнера>
```
### Список команд перезапуска отдельных контейнеров:
Redis
```angular2html
docker compose restart redis
```
Nginx
```angular2html
docker compose restart nginx
```
PostgreSQL
```angular2html
docker compose restart postgres
```

Gunicorn
```angular2html
docker compose restart web
```
Проверка файла конфигурации на наличие ошибок
```angular2html
docker compose exec nginx nginx -t
```
Проверка логов, которые можно настроить для fail2ban, а так же выявлять запросы к ввашему серверу на VPS
```angular2html
docker compose logs nginx --tail 20
```
Перезапуск Nginx при изменениях **config** файла без полной остановки и перезапуска контейнера.
```angular2html
docker compose exec nginx nginx -s reload
```
Проверка логов сервисов:

Redis
```angular2html
docker compose logs redis --tail 20
```

Gunicorn:
```angular2html
docker compose logs web --tail 20
```
PostgreSQL:
```angular2html
docker compose logs db --tail 20
```
Проверка, принимает ли база подключения:
```angular2html
docker compose exec db pg_isready -U <USER_NAME>
```
Redis (Проверка отклика)
```angular2html
docker compose exec redis redis-cli ping
```


Логи всего Docker compose
```angular2html
docker compose logs -f
```
Если необходимо перезапустить контейнеры
```angular2html
docker compose restart
```
Если необходимо, пересоберите контейнеры
```angular2html
docker compose down -v
docker compose up -d --build
```
Вышеуказаные команды выполнять находясь в папке
```angular2html
cd /var/www/it-linux
```
### Создайте группу модераторов
```angular2html
docker compose exec web python manage.py create_moderators
```
Если нужно отчистить БД

```angular2html
docker compose exec web python manage.py flush --noinput
```

### Удаление проекта с VPS
```angular2html
cd /var/www/it-linux
docker compose down -v
cd /var/www/
sudo rm -r it-linux
cd
```
Чтобы удалить
все контейнеры (и запущенные, и остановленные) одной командой, используйте:
```angular2html
docker rm -f $(docker ps -aq)

```


Автор: Казанцев Андрей