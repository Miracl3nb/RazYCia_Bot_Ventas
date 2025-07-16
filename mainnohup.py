import os
import asyncio
import hashlib
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Configurar logging para archivo únicamente
log_filename = f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        # Removido StreamHandler para evitar salida por consola
    ]
)
logger = logging.getLogger(__name__)

# Suprimir logs de urllib3 y telegram que pueden generar ruido
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

load_dotenv()

# 🔐 Token del bot
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 📁 Rutas de carpetas
BASE_DIR = os.path.dirname(__file__)
MEDIA_FOLDER = os.path.join(BASE_DIR, "MEDIA")
TUTORIALES_FOLDER = os.path.join(MEDIA_FOLDER, "Tutoriales")

# 🚀 CACHE AVANZADO - Incluye hash y fecha de archivos
CACHED_FILES = {}
FILE_HASHES = {}

# Lista de administradores (agregar user_ids reales)
ADMIN_IDS = [123456789]  # Reemplazar con user_ids reales

def get_file_hash(file_path):
    """Obtiene el hash MD5 de un archivo para detectar cambios"""
    try:
        if not os.path.exists(file_path):
            return None
        
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Error calculando hash para {file_path}: {e}")
        return None

def file_has_changed(file_path, key):
    """Verifica si un archivo ha cambiado desde la última vez"""
    current_hash = get_file_hash(file_path)
    if current_hash is None:
        return False
    
    # Si no tenemos hash previo, es un archivo nuevo
    if key not in FILE_HASHES:
        FILE_HASHES[key] = current_hash
        return True
    
    # Si el hash cambió, el archivo fue modificado
    if FILE_HASHES[key] != current_hash:
        FILE_HASHES[key] = current_hash
        return True
    
    return False

async def send_cached_file(update: Update, file_path: str, file_type: str, key: str, caption: str):
    """Envía archivo usando cache con manejo de errores automático"""
    
    # Verificar si el archivo cambió
    if file_has_changed(file_path, key):
        logger.info(f"🔄 Archivo {key} cambió - eliminando cache anterior")
        # Eliminar cache anterior si existe
        if key in CACHED_FILES:
            del CACHED_FILES[key]
    
    # Si está en cache y no cambió, intentar enviarlo
    if key in CACHED_FILES:
        try:
            if file_type == "video":
                await update.message.reply_video(CACHED_FILES[key], caption=caption)
                logger.info(f"✅ {key} enviado desde cache")
                return True
            elif file_type == "document":
                await update.message.reply_document(CACHED_FILES[key], caption=caption)
                logger.info(f"✅ {key} enviado desde cache")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Error enviando {key} desde cache: {e}")
            logger.info(f"🔄 Eliminando cache inválido y recargando...")
            # Eliminar cache inválido
            del CACHED_FILES[key]
            if key in FILE_HASHES:
                del FILE_HASHES[key]
    
    # Si no está en cache o falló, cargar desde archivo
    if os.path.exists(file_path):
        try:
            logger.info(f"📤 Enviando {key} desde archivo local...")
            with open(file_path, "rb") as file:
                if file_type == "video":
                    message = await update.message.reply_video(video=file, caption=caption)
                    CACHED_FILES[key] = message.video.file_id
                    FILE_HASHES[key] = get_file_hash(file_path)
                elif file_type == "document":
                    message = await update.message.reply_document(
                        document=file, 
                        filename=f"{key}.pdf", 
                        caption=caption
                    )
                    CACHED_FILES[key] = message.document.file_id
                    FILE_HASHES[key] = get_file_hash(file_path)
            
            logger.info(f"✅ {key} enviado y cacheado con file_id: {CACHED_FILES[key][:20]}...")
            return True
        except Exception as e:
            logger.error(f"❌ Error enviando {key}: {e}")
            return False
    
    logger.warning(f"⚠️ Archivo {file_path} no encontrado")
    return False

def is_admin(user_id):
    """Verifica si el usuario es administrador"""
    return user_id in ADMIN_IDS

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores del bot"""
    logger.error(f"Error en update {update}: {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ Ocurrió un error. Intenta nuevamente.")

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_name} (ID: {user_id}) ejecutó /start")
    
    mensaje = (
        f"👋 ¡Hola {user_name}! Soy el asistente.\n\n"
        "📌 **Comandos disponibles:**\n"
        "🔧 /instalar - Ver tutoriales de instalación\n"
        "📲 /ingresar - Instrucciones para ingresar a la app\n"
        "🔑 /clave - Ayuda para resetear tu clave\n"
        "📝 /pasar_pedido - Cómo pasar un pedido\n"
        "📊 /cache_status - Ver estado del cache\n"
        "🧹 /clear_cache - Limpiar cache (solo admin)\n"
        "🔍 /debug_cache - Debug detallado del cache (solo admin)\n"
        "🧪 /force_cache - Forzar recache de archivos (solo admin)\n"
        "❓ /ayuda - Mostrar este mensaje"
    )
    await update.message.reply_text(mensaje, parse_mode='Markdown')

# /ayuda - Alias para /start
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# Bienvenida mejorada
async def bienvenida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_user in update.message.new_chat_members:
        logger.info(f"Nuevo miembro: {new_user.first_name} (ID: {new_user.id})")
        await update.message.reply_text(
            f"👋 ¡Bienvenido/a, {new_user.first_name}!\n\n"
            "🤖 Comandos de ayuda disponibles:\n\n"
            "🔧 /instalar – Tutoriales de instalación\n"
            "📲 /ingresar – Instrucciones para ingresar a la app\n"
            "🔑 /clave – Cómo resetear tu clave\n"
            "📝 /pasar_pedido – Cómo pasar un pedido\n"
            #"❓ /ayuda – Ver todos los comandos",
            #parse_mode='Markdown'
        )

# /instalar - CON MANEJO DE ERRORES AUTOMÁTICO ⚡
async def instalar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_id} ejecutó /instalar")
    
    await update.message.reply_text("🎬 Enviando tutoriales de instalación...")
    
    # Rutas de videos
    videos = [
        ("Samsung.mp4", "Samsung", "📹 Samsung - Tutorial de instalación"),
        ("Xiaomi.mp4", "Xiaomi", "📹 Xiaomi - Tutorial de instalación")
    ]
    
    # Enviar videos con manejo automático de errores
    tasks = []
    
    for video_file, key, caption in videos:
        video_path = os.path.join(MEDIA_FOLDER, video_file)
        
        if os.path.exists(video_path):
            tasks.append(send_cached_file(update, video_path, "video", key, caption))
        else:
            tasks.append(update.message.reply_text(f"⚠️ Video {key} no encontrado"))
    
    # Ejecutar en paralelo
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Contar éxitos
    success_count = sum(1 for result in results if result is True)
    total_count = len(videos)
    
    logger.info(f"Tutoriales enviados: {success_count}/{total_count}")
    await update.message.reply_text(
        f"✅ Tutoriales enviados: {success_count}/{total_count}"
    )

# /pasar_pedido - CON MANEJO DE ERRORES AUTOMÁTICO ⚡
async def pasar_pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_id} ejecutó /pasar_pedido")
    
    await update.message.reply_text("🎬 Enviando tutorial de pedidos...")
    
    video_path = os.path.join(MEDIA_FOLDER, "PasarPedido.mp4")
    
    success = await send_cached_file(
        update, video_path, "video", "pasar_pedido", 
        "📹 App Ventas - Tutorial de pasar pedido"
    )
    
    if not success:
        await update.message.reply_text("⚠️ Video PasarPedido no encontrado")

# /ingresar - CON MANEJO DE ERRORES AUTOMÁTICO ⚡
async def ingresar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_id} ejecutó /ingresar")
    
    await update.message.reply_text("📲 Instrucciones para ingresar a la app:")
    
    pdf_path = os.path.join(TUTORIALES_FOLDER, "ingresar.pdf")
    
    success = await send_cached_file(
        update, pdf_path, "document", "ingresar", 
        "📄 Instrucciones detalladas en PDF"
    )
    
    if not success:
        await update.message.reply_text("⚠️ No se encontró el archivo ingresar.pdf")

# /clave - CON MANEJO DE ERRORES AUTOMÁTICO ⚡
async def clave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_id} ejecutó /clave")
    
    await update.message.reply_text("🔐 Cómo resetear tu clave:")
    
    pdf_path = os.path.join(TUTORIALES_FOLDER, "clave.pdf")
    
    success = await send_cached_file(
        update, pdf_path, "document", "clave", 
        "📄 Instrucciones para resetear la clave"
    )
    
    if not success:
        await update.message.reply_text("⚠️ No se encontró el archivo clave.pdf")

#func comando instalar Thunderbird a espera de videos ----> A CONTINUAR 
async def instalar_Thunderbird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_id} ejecutó /pasar_pedido")
    
    await update.message.reply_text("🎬 Enviando tutorial de pedidos...")
    
    video_path = os.path.join(MEDIA_FOLDER, "PasarPedido.mp4")
    
    success = await send_cached_file(
        update, video_path, "video", "pasar_pedido", 
        "📹 App Ventas - Tutorial de pasar pedido"
    )
    
    if not success:
        await update.message.reply_text("⚠️ Video PasarPedido no encontrado")


#func comando configurar Thunderbird a espera de videos ----> A CONTINUAR 
async def configurar_Thunderbird(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_id} ejecutó /pasar_pedido")
    
    await update.message.reply_text("🎬 Enviando tutorial de pedidos...")
    
    video_path = os.path.join(MEDIA_FOLDER, "PasarPedido.mp4")
    
    success = await send_cached_file(
        update, video_path, "video", "pasar_pedido", 
        "📹 App Ventas - Tutorial de pasar pedido"
    )
    
    if not success:
        await update.message.reply_text("⚠️ Video PasarPedido no encontrado")

# 🔍 COMANDO DEBUG PARA VERIFICAR CACHE Y ARCHIVOS
async def debug_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug del estado del cache y archivos"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        logger.warning(f"Usuario no admin {user_id} intentó usar debug_cache")
        await update.message.reply_text("❌ Solo los administradores pueden usar este comando.")
        return
    
    logger.info(f"Admin {user_id} ejecutó debug_cache")
    
    debug_info = "🔍 **DEBUG CACHE:**\n\n"
    
    # Estado del cache
    debug_info += f"📊 **Archivos en cache:** {len(CACHED_FILES)}\n"
    debug_info += f"📊 **Hashes guardados:** {len(FILE_HASHES)}\n\n"
    
    # Verificar archivos de video
    videos_to_check = [
        ("Samsung.mp4", "samsung"),
        ("Xiaomi.mp4", "xiaomi"),
        ("PasarPedido.mp4", "pasar_pedido")
    ]
    
    debug_info += "🎬 **VIDEOS:**\n"
    for video_file, key in videos_to_check:
        video_path = os.path.join(MEDIA_FOLDER, video_file)
        exists = os.path.exists(video_path)
        cached = key in CACHED_FILES
        current_hash = get_file_hash(video_path) if exists else "N/A"
        stored_hash = FILE_HASHES.get(key, "N/A")
        
        debug_info += f"• **{video_file}**\n"
        debug_info += f"  └ Existe: {'✅' if exists else '❌'}\n"
        debug_info += f"  └ En cache: {'✅' if cached else '❌'}\n"
        debug_info += f"  └ Hash actual: `{current_hash[:8]}...`\n"
        debug_info += f"  └ Hash guardado: `{stored_hash[:8] if stored_hash != 'N/A' else 'N/A'}...`\n"
        
        if cached:
            file_id = CACHED_FILES[key]
            debug_info += f"  └ File ID: `{file_id[:15]}...`\n"
        
        debug_info += "\n"
    
    # Verificar PDFs ACA AGREGAR LOS .PDF QUE SE SUMEN
    pdfs_to_check = [
        ("ingresar.pdf", "ingresar"),
        ("clave.pdf", "clave")
    ]
    
    debug_info += "📄 **PDFs:**\n"
    for pdf_file, key in pdfs_to_check:
        pdf_path = os.path.join(TUTORIALES_FOLDER, pdf_file)
        exists = os.path.exists(pdf_path)
        cached = key in CACHED_FILES
        current_hash = get_file_hash(pdf_path) if exists else "N/A"
        stored_hash = FILE_HASHES.get(key, "N/A")
        
        debug_info += f"• **{pdf_file}**\n"
        debug_info += f"  └ Existe: {'✅' if exists else '❌'}\n"
        debug_info += f"  └ En cache: {'✅' if cached else '❌'}\n"
        debug_info += f"  └ Hash actual: `{current_hash[:8]}...`\n"
        debug_info += f"  └ Hash guardado: `{stored_hash[:8] if stored_hash != 'N/A' else 'N/A'}...`\n"
        
        if cached:
            file_id = CACHED_FILES[key]
            debug_info += f"  └ File ID: `{file_id[:15]}...`\n"
        
        debug_info += "\n"
    
    await update.message.reply_text(debug_info, parse_mode='Markdown')

# 🧪 COMANDO PARA FORZAR ReCache
async def force_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fuerza el cache de todos los archivos"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        logger.warning(f"Usuario no admin {user_id} intentó usar force_cache")
        await update.message.reply_text("❌ Solo los administradores pueden usar este comando.")
        return
    
    logger.info(f"Admin {user_id} ejecutó force_cache")
    
    await update.message.reply_text("🔄 Forzando recache de todos los archivos...")
    
    # Limpiar cache actual
    global CACHED_FILES, FILE_HASHES
    CACHED_FILES.clear()
    FILE_HASHES.clear()
    
    # Forzar recache de videos ACA SUMAR .MP4 QUE SE SUMEN
    videos = [
        ("Samsung.mp4", "samsung", "📹 Samsung - Tutorial de instalación"),
        ("Xiaomi.mp4", "xiaomi", "📹 Xiaomi - Tutorial de instalación"),
        ("PasarPedido.mp4", "pasar_pedido", "📹 App Ventas - Tutorial de pasar pedido")
    ]
    
    success_count = 0
    for video_file, key, caption in videos:
        video_path = os.path.join(MEDIA_FOLDER, video_file)
        if os.path.exists(video_path):
            try:
                with open(video_path, "rb") as file:
                    message = await update.message.reply_video(video=file, caption=caption)
                    CACHED_FILES[key] = message.video.file_id
                    FILE_HASHES[key] = get_file_hash(video_path)
                    success_count += 1
                    logger.info(f"✅ {key} cacheado con ID: {CACHED_FILES[key][:20]}...")
            except Exception as e:
                logger.error(f"❌ Error cacheando {key}: {e}")
        else:
            logger.warning(f"⚠️ Archivo {video_path} no encontrado")
    
    # Forzar recache de PDFs
    pdfs = [
        ("ingresar.pdf", "ingresar", "📄 Instrucciones detalladas en PDF"),
        ("clave.pdf", "clave", "📄 Instrucciones para resetear la clave")
    ]
    
    for pdf_file, key, caption in pdfs:
        pdf_path = os.path.join(TUTORIALES_FOLDER, pdf_file)
        if os.path.exists(pdf_path):
            try:
                with open(pdf_path, "rb") as file:
                    message = await update.message.reply_document(
                        document=file, 
                        filename=pdf_file, 
                        caption=caption
                    )
                    CACHED_FILES[key] = message.document.file_id
                    FILE_HASHES[key] = get_file_hash(pdf_path)
                    success_count += 1
                    logger.info(f"✅ {key} cacheado con ID: {CACHED_FILES[key][:20]}...")
            except Exception as e:
                logger.error(f"❌ Error cacheando {key}: {e}")
        else:
            logger.warning(f"⚠️ Archivo {pdf_path} no encontrado")
    
    logger.info(f"Recache completado - {success_count} archivos cacheados")
    await update.message.reply_text(
        f"✅ **Recache completado!**\n"
        f"📊 Archivos cacheados: {success_count}\n"
        f"📈 Total en cache: {len(CACHED_FILES)}"
    )

async def cache_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Usuario {user_id} ejecutó cache_status")
    
    status = "📊 **Estado del Cache:**\n\n"
    
    if not CACHED_FILES:
        status += "❌ No hay archivos en cache\n"
    else:
        for key, file_id in CACHED_FILES.items():
            file_hash = FILE_HASHES.get(key, "Sin hash")
            status += f"✅ **{key.capitalize()}**\n"
            status += f"   └ ID: `{file_id[:20]}...`\n"
            status += f"   └ Hash: `{file_hash[:8]}...`\n\n"
    
    status += f"📈 **Total archivos en cache:** {len(CACHED_FILES)}"
    
    await update.message.reply_text(status, parse_mode='Markdown')

# 🧹 COMANDO PARA LIMPIAR CACHE (SOLO ADMIN)
async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        logger.warning(f"Usuario no admin {user_id} intentó usar clear_cache")
        await update.message.reply_text("❌ Solo los administradores pueden limpiar el cache.")
        return
    
    logger.info(f"Admin {user_id} ejecutó clear_cache")
    
    global CACHED_FILES, FILE_HASHES
    files_count = len(CACHED_FILES)
    
    CACHED_FILES.clear()
    FILE_HASHES.clear()
    
    logger.info(f"Cache limpiado - {files_count} archivos eliminados")
    await update.message.reply_text(
        f"🧹 **Cache limpiado exitosamente!**\n"
        f"📊 Se eliminaron {files_count} archivos del cache."
    )

# Crear directorios si no existen
def ensure_directories():
    """Crea las carpetas necesarias si no existen"""
    directories = [MEDIA_FOLDER, TUTORIALES_FOLDER]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"📁 Creado directorio: {directory}")

# Main
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN no encontrado en variables de entorno")
        return
    
    ensure_directories()
    logger.info("🤖 Iniciando bot con cache inteligente...")
    logger.info(f"📝 Logs se guardarán en: {log_filename}")
    
    try:
        # Configurar bot con timeouts optimizados
        app = ApplicationBuilder()\
            .token(BOT_TOKEN)\
            .read_timeout(60)\
            .write_timeout(60)\
            .connect_timeout(60)\
            .pool_timeout(20)\
            .build()
        
        # Registrar handlers
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bienvenida))
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("ayuda", ayuda))
        app.add_handler(CommandHandler("instalar", instalar))
        app.add_handler(CommandHandler("ingresar", ingresar))
        app.add_handler(CommandHandler("clave", clave))
        app.add_handler(CommandHandler("pasar_pedido", pasar_pedido))
        app.add_handler(CommandHandler("cache_status", cache_status))
        app.add_handler(CommandHandler("clear_cache", clear_cache))
        app.add_handler(CommandHandler("debug_cache", debug_cache))
        app.add_handler(CommandHandler("force_cache", force_cache))
        
        # Agregar handler de errores
        app.add_error_handler(error_handler)

        logger.info("🚀 Bot iniciado correctamente y corriendo...")
        app.run_polling()
    
    except Exception as e:
        logger.error(f"❌ Error crítico al iniciar el bot: {e}")
    finally:
        logger.info("🛑 Bot detenido")

if __name__ == "__main__":
    main()