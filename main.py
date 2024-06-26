from fastapi import Depends, FastAPI, HTTPException, status, Response, Security, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, SecurityScopes
from functools import lru_cache
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.sql import func
from sqlalchemy import and_
from sqlalchemy.sql.expression import case
from sqlalchemy import desc, asc
from sqlalchemy import text
from uuid import uuid4
from pathlib import Path
from typing import Union
from datetime import datetime, timedelta
#---Imported for JWT example-----------
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError
from typing_extensions import Annotated
import models
import schemas
from database import SessionLocal, engine 
import init_db
import config
import asyncio
import concurrent.futures
import csv
from io import BytesIO, StringIO
from fastapi.responses import StreamingResponse
from fastapi import File, UploadFile
import codecs
import json
#FOR MACHONE LEARNING
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import skforecast
from skforecast.ForecasterAutoreg import ForecasterAutoreg



models.Base.metadata.create_all(bind=engine)

#Create resources for JWT flow
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(
	tokenUrl="token",
	scopes={"admin": "Add, edit and delete all information.", "investigador": "add, edit and read some information.", "cliente": "Read relevant information.", "usuario": "Only read about us information"}
)
#----------------------
#Create our main app
app = FastAPI()

#----SETUP MIDDLEWARES--------------------

# Allow these origins to access the API
origins = [	
	"http://proj-precipitaciones.onrender.com",
	"https://proj-precipitaciones.onrender.com",		
	"http://localhost",
	"http://localhost:8080",
	"https://localhost:8080",
	"http://localhost:5000",
	"https://localhost:5000",
	"http://localhost:3000",
	"https://localhost:3000",
	"http://localhost:8000",
	"https://localhost:8000",
]

# Allow these methods to be used
methods = ["GET", "POST", "PUT", "DELETE"]

# Only these headers are allowed
headers = ["Content-Type", "Authorization"]

app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=methods,
	allow_headers=headers,
	expose_headers=["*"]
)

ALGORITHM = config.ALGORITHM	
SECRET_KEY = config.SECRET_KEY
APP_NAME = config.APP_NAME
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES
ADMIN_USER = config.ADMIN_USER
ADMIN_NOMBRE = config.ADMIN_NOMBRE
ADMIN_PAPELLIDO = config.ADMIN_PAPELLIDO
ADMIN_SAPELLIDO = config.ADMIN_SAPELLIDO
ADMIN_CI = config.ADMIN_CI
ADMIN_CORREO = config.ADMIN_CORREO
ADMIN_PASS = config.ADMIN_PASS

# Dependency
def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


#------CODE FOR THE JWT EXAMPLE----------
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(db: Session, username: str):
	db_user = db.query(models.User).filter(models.User.username == username).first()	
	if db_user is not None:
		return db_user 

#This function is used by "login_for_access_token"
def authenticate_user(username: str, password: str,  db: Session = Depends(get_db)):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password): #secret
        return False
    return user
	
#This function is used by "login_for_access_token"
def create_access_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=30) #Si no se pasa un valor por usuario
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
	
#This function is used by "get currecnt active user" dependency security authentication
async def get_current_user(
			security_scopes: SecurityScopes, 
			token: Annotated[str, Depends(oauth2_scheme)],
			db: Session = Depends(get_db)):
	if security_scopes.scopes:
		authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
	else:
		authenticate_value = "Bearer"
		
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	try:
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
		username: str = payload.get("sub")
		if username is None:
			raise credentials_exception			
		token_scopes = payload.get("scopes", [])
		token_data = schemas.TokenData(scopes=token_scopes, username=username)
		
	except (JWTError, ValidationError):
		raise credentials_exception
			
		token_data = schemas.TokenData(username=username)
	except JWTError:
		raise credentials_exception
		
	user = get_user(db, username=token_data.username)
	if user is None:
		raise credentials_exception
		
	for user_scope in security_scopes.scopes:
		if user_scope not in token_data.scopes:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Not enough permissions",
				headers={"WWW-Authenticate": authenticate_value},
			)
			
	return user
	
async def get_current_active_user(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["admin"])]):  #, "manager", "user"
	if current_user.disable:
		print({"USER AUTENTICATED" : current_user.disable})
		print({"USER ROLES" : current_user.role})
		raise HTTPException(status_code=400, detail="Disable user")
	return current_user

#------------------------------------
@app.post("/token", response_model=schemas.Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
	user = authenticate_user(form_data.username, form_data.password, db)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Incorrect username or password",
			headers={"WWW-Authenticate": "Bearer"},
		)
	access_token_expires = timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
	print(form_data.scopes)
	
	print(user.role) #Prin my roles to confirm them
	
	access_token = create_access_token(
		data={"sub": user.username, "scopes": user.role},   #form_data.scopes
		expires_delta=access_token_expires
	)
	return {"detail": "Ok", "access_token": access_token, "token_type": "Bearer"}
	
@app.get("/")
def index():
	return {"Application": "Hidro application"}
	
@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: Annotated[schemas.User, Depends(get_current_user)]):
	return current_user

@app.get("/get_restricted_user")
async def get_restricted_user(current_user: Annotated[schemas.User, Depends(get_current_active_user)]):
    return current_user
	
@app.get("/get_authenticated_edition_resources", response_model=schemas.User)
async def get_authenticated_edition_resources(current_user: Annotated[schemas.User, Security(get_current_active_user, scopes=["investigador"])]):
    return current_user
	
@app.get("/get_authenticated_read_resources", response_model=schemas.User)
async def get_authenticated_read_resources(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["cliente"])]):
    return current_user
	
#########################
###   USERS ADMIN  ######
#########################
@app.post("/create_owner", status_code=status.HTTP_201_CREATED)  
async def create_owner(db: Session = Depends(get_db)): #Por el momento no tiene restricciones
	if db.query(models.User).filter(models.User.username == config.ADMIN_USER).first():
		db_user = db.query(models.User).filter(models.User.username == config.ADMIN_USER).first()
		if db_user is None:
			raise HTTPException(status_code=404, detail="El usuario no existe en la base de datos")	
		db.delete(db_user)	
		db.commit()
		
	db_user = models.User(
		username=config.ADMIN_USER, 
		nombre=config.ADMIN_NOMBRE,
		primer_appellido=config.ADMIN_PAPELLIDO,
		segundo_appellido=config.ADMIN_SAPELLIDO,
		ci=config.ADMIN_CI,
		email=config.ADMIN_CORREO,
		role=["admin","investigador","cliente","usuario"],
		disable=False,
		hashed_password=pwd_context.hash(config.ADMIN_PASS)		
	)
	db.add(db_user)
	db.commit()
	db.refresh(db_user)	
	return {f"Resultado:": "Usuario creado satisfactoriamente"}
	
@app.post("/crear_usuario/", status_code=status.HTTP_201_CREATED)  
async def crear_usuario(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
				user: schemas.UserAdd, db: Session = Depends(get_db)): 
	if db.query(models.User).filter(models.User.username == user.username).first() :
		raise HTTPException( 
			status_code=400,
			detail="El usuario existe en la base de datos",
		)	
	db_user = models.User(
		username=user.username, 
		nombre=user.nombre,
		primer_appellido=user.primer_appellido,
		segundo_appellido=user.segundo_appellido,
		ci=user.ci,
		email=user.email,
		role=user.role,
		disable=True,
		hashed_password=pwd_context.hash(user.hashed_password)
	)
	db.add(db_user)
	db.commit()
	db.refresh(db_user)	
	return {f"Usuario: {db_user.username}": "creado satisfactoriamente"}
	
@app.get("/leer_usuarios/", status_code=status.HTTP_201_CREATED) 
async def leer_usuarios(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
		skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):    	
	db_users = db.query(models.User).offset(skip).limit(limit).all()    
	return db_users
	

@app.put("/actualizar_usuario/{username}", status_code=status.HTTP_201_CREATED) 
async def actualizar_usuario(current_user: Annotated[schemas.User, Depends(get_current_active_user)], 
				username: str, new_user: schemas.UserUPD, db: Session = Depends(get_db)):
	db_user = db.query(models.User).filter(models.User.username == username).first()
	if db_user is None:
		raise HTTPException(status_code=404, detail="Usuario no encontrado")
	db_user.nombre=new_user.nombre	
	db_user.primer_appellido=new_user.primer_appellido
	db_user.segundo_appellido=new_user.segundo_appellido
	db_user.ci=new_user.ci	
	db_user.email=new_user.email	
	db_user.role=new_user.role
	db.commit()
	db.refresh(db_user)	
	return db_user	
	
@app.put("/activar_usuario/{username}", status_code=status.HTTP_201_CREATED) 
async def activar_usuario(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
				username: str, new_user: schemas.UserActivate, db: Session = Depends(get_db)):
	db_user = db.query(models.User).filter(models.User.username == username).first()
	if db_user is None:
		raise HTTPException(status_code=404, detail="Usuario no encontrado")
	if username != "_admin" and username != current_user.username:
		db_user.disable=new_user.disable		
		db.commit()
		db.refresh(db_user)	
	return db_user	
	
@app.delete("/eliminar_usuario/{username}", status_code=status.HTTP_201_CREATED) 
async def eliminar_usuario(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
				username: str, db: Session = Depends(get_db)):
	db_user = db.query(models.User).filter(models.User.username == username).first()
	if db_user is None:
		raise HTTPException(status_code=404, detail="Usuario no encontrado")	
	if username != "_admin" and username != current_user.username:
		db.delete(db_user)	
		db.commit()
	return {"Deleted": "Usuario eliminado satisfactoriamente"}
	
@app.put("/actualizar_contrasenna/{username}", status_code=status.HTTP_201_CREATED) 
async def actualizar_contrasenna(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])],
				username: str, password: schemas.UserPassword, db: Session = Depends(get_db)):
	db_user = db.query(models.User).filter(models.User.username == username).first()
	if db_user is None:
		raise HTTPException(status_code=404, detail="Usuario no encontrado")	
	db_user.hashed_password=pwd_context.hash(password.hashed_password)
	db.commit()
	db.refresh(db_user)	
	return {"Result": "Contrasenna actualizada satisfactoriamente"}
	
@app.put("/actualizar_contrasenna_por_usuario/{username}", status_code=status.HTTP_201_CREATED) 
async def actualizar_contrasenna_por_usuario(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])],
				username: str, password: schemas.UserResetPassword, db: Session = Depends(get_db)):
				
	if not verify_password(password.actualpassword, current_user.hashed_password): 
		return HTTPException(status_code=700, detail="La cotrasenna actual no coincide")
		
	db_user = db.query(models.User).filter(models.User.username == username).first()	
	if db_user is None:
		raise HTTPException(status_code=404, detail="Usuario no encontrado")	
	db_user.hashed_password=pwd_context.hash(password.newpassword)
	db.commit()
	db.refresh(db_user)	
	return {"Response": "Contrasenna actualizada satisfactoriamente"}
		
#############################
####  ENTIDAD ORIGEN  #######
#############################
@app.post("/crear_provincia/", status_code=status.HTTP_201_CREATED)
async def crear_provincia(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					provincia: schemas.Provincias, db: Session = Depends(get_db)):
	try:
		db_provincia = models.Provincias(
			nombre_provincia = provincia.nombre_provincia,
			codigo_provincia = provincia.codigo_provincia
		)			
		db.add(db_provincia)   	
		db.commit()
		db.refresh(db_provincia)			
		return {"Result":"Provincia creada satisfactoriamente"}
		
	except IntegrityError as e:
		raise HTTPException(status_code=500, detail="Error de integridad creando objeto Provincia")
	except SQLAlchemyError as e: 
		raise HTTPException(status_code=405, detail="Error inesperado creando el objeto Provincia")		

@app.get("/leer_provincias/", status_code=status.HTTP_201_CREATED)  
async def leer_provincias(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])],
					skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):    
	
	db_provincias = db.query(models.Provincias).all()	
	
	return db_provincias
	
@app.delete("/eliminar_provincia/{id}", status_code=status.HTTP_201_CREATED) 
async def eliminar_provincia(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					id: str, db: Session = Depends(get_db)):
	db_provincia = db.query(models.Provincias
						).filter(models.Provincias.id_provincia == id
						).first()
	if db_provincia is None:
		raise HTTPException(status_code=404, detail="La Provincia no existe en la base de datos")	
	db.delete(db_provincia)	
	db.commit()
	return {"Result": "Provincia eliminada satisfactoriamente"}
	
@app.put("/actualizar_provincia/{id}", status_code=status.HTTP_201_CREATED) 
async def actualizar_provincia(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])], 
				id: str, provincia: schemas.Provincias, db: Session = Depends(get_db)):
	
	db_provincia = db.query(models.Provincias).filter(models.Provincias.id_provincia == id).first()
	
	if db_provincia is None:
		raise HTTPException(status_code=404, detail="La provincia no existen en la base de datos")
	
	db_provincia.org_nombre = provincia.nombre_provincia	
	db_provincia.codigo_provincia = provincia.codigo_provincia
	
	db.commit()
	db.refresh(db_provincia)	
	return {"Result": "Provincia actualizada satisfactoriamente"}	
	
#############################
#######   MUNICIPIO  ########
#############################
@app.post("/crear_municipio/", status_code=status.HTTP_201_CREATED)
async def crear_municipio(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					municipio: schemas.Municipios, db: Session = Depends(get_db)):
	
	db_provincia = db.query(models.Provincias).filter(models.Provincias.id_provincia == municipio.provincia_id).first()
	
	if db_provincia is None:
		raise HTTPException(status_code=404, detail="La provincia no existen en la base de datos")
	
	try:
		db_municipio = models.Municipios(
			nombre_municipio = municipio.nombre_municipio,
			provincia_id = municipio.provincia_id,
		)			
		db.add(db_municipio)   	
		db.commit()
		db.refresh(db_municipio)			
		return db_municipio
		
	except IntegrityError as e:
		raise HTTPException(status_code=500, detail="Error de integridad creando objeto Municipio")
	except SQLAlchemyError as e: 
		raise HTTPException(status_code=405, detail="Error inesperado creando el objeto Municipio")		

@app.get("/leer_municipios/", status_code=status.HTTP_201_CREATED)  
async def leer_municipios(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])],
					skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):    
	 
	db_municipios = db.query(
						models.Municipios.id_municipio,
						models.Municipios.nombre_municipio,
						models.Municipios.provincia_id,
						models.Provincias.nombre_provincia,
						models.Provincias.codigo_provincia
					).select_from(models.Municipios
					).join(models.Provincias, models.Provincias.id_provincia == models.Municipios.provincia_id
					).all()	
	
	return db_municipios
	
@app.delete("/eliminar_municipio/{id}", status_code=status.HTTP_201_CREATED) 
async def eliminar_municipio(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					id: str, db: Session = Depends(get_db)):
	
	db_municipio = db.query(models.Municipios
						).filter(models.Municipios.id_municipio == id
						).first()
	
	if db_municipio is None:
		raise HTTPException(status_code=404, detail="El municipio no existe en la base de datos")	
	
	db.delete(db_municipio)	
	db.commit()
	return {"Result": "Municipio eliminada satisfactoriamente"}
	
@app.put("/actualizar_municipio/{id}", status_code=status.HTTP_201_CREATED) 
async def actualizar_municipio(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])], 
				id: str, municipio: schemas.Municipios_UPD, db: Session = Depends(get_db)):
	
	db_municipio = db.query(models.Municipios).filter(models.Municipios.id_municipio == id).first()
	
	if db_municipio is None:
		raise HTTPException(status_code=404, detail="El municipio seleccionado no existe en la base de datos")
	
	db_municipio.nombre_municipio = municipio.nombre_municipio
	
	db.commit()
	db.refresh(db_municipio)	
	
	return {"Result": "Municipio actualizado satisfactoriamente"}	


#############################
#######  ESTACIONES  ########
#############################
@app.post("/crear_estacion/", status_code=status.HTTP_201_CREATED)
async def crear_estacion(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					estacion: schemas.Estaciones, db: Session = Depends(get_db)):
	
	db_municipio = db.query(models.Municipios).filter(models.Municipios.id_municipio == estacion.municipio_id).first()
	
	if db_municipio is None:
		raise HTTPException(status_code=404, detail="El municipio existe en la base de datos")
	
	try:
		db_estacion = models.Estaciones(
			nombre_estacion = estacion.nombre_estacion,
			codigo_estacion = estacion.codigo_estacion,
			altura_estacion = estacion.altura_estacion,
			norte_estacion = estacion.norte_estacion,
			sur_estacion = estacion.sur_estacion,
			municipio_id = estacion.municipio_id,
		)			
		db.add(db_estacion)   	
		db.commit()
		db.refresh(db_estacion)			
		return db_estacion
		
	except IntegrityError as e:
		raise HTTPException(status_code=500, detail="Error de integridad creando objeto Estacion")
	except SQLAlchemyError as e: 
		raise HTTPException(status_code=405, detail="Error inesperado creando el objeto Estacion")		

@app.get("/leer_estaciones/", status_code=status.HTTP_201_CREATED)  
async def leer_estaciones(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])],
					skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):    
	
	db_estaciones = db.query(
						models.Estaciones.id_estacion,
						models.Estaciones.nombre_estacion,
						models.Estaciones.codigo_estacion,
						models.Estaciones.altura_estacion,
						models.Estaciones.norte_estacion,
						models.Estaciones.sur_estacion,
						models.Estaciones.municipio_id,
						models.Municipios.nombre_municipio
					).select_from(models.Estaciones
					).join(models.Municipios, models.Municipios.id_municipio == models.Estaciones.municipio_id
					).all()	
	
	return db_estaciones
	
@app.delete("/eliminar_estacion/{id}", status_code=status.HTTP_201_CREATED) 
async def eliminar_estacion(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					id: str, db: Session = Depends(get_db)):
	
	db_estacion = db.query(models.Estaciones
						).filter(models.Estaciones.id_estacion == id
						).first()
	
	if db_estacion is None:
		raise HTTPException(status_code=404, detail="La estacion no existe en la base de datos")	
	
	db.delete(db_estacion)	
	db.commit()
	return {"Result": "Estacion eliminada satisfactoriamente"}
	
@app.put("/actualizar_estacion/{id}", status_code=status.HTTP_201_CREATED) 
async def actualizar_estacion(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])], 
				id: str, estacion: schemas.Estaciones_UPD, db: Session = Depends(get_db)):
	
	db_estacion = db.query(models.Estaciones).filter(models.Estaciones.id_estacion == id).first()
	
	if db_estacion is None:
		raise HTTPException(status_code=404, detail="La estacion seleccionada no existe en la base de datos")
	
	db_estacion.nombre_estacion = estacion.nombre_estacion
	
	db.commit()
	db.refresh(db_estacion)	
	
	return {"Result": "Estacion actualizada satisfactoriamente"}

#############################
##########  DATOS  ##########
#############################
@app.post("/crear_dato/", status_code=status.HTTP_201_CREATED)
async def crear_dato(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					dato: schemas.Datos, db: Session = Depends(get_db)):
	
	db_estacion = db.query(models.Estaciones).filter(models.Estaciones.id_estacion == dato.estacion_id).first()
	
	if db_estacion is None:
		raise HTTPException(status_code=404, detail="La estacion no existen en la base de datos")
	
	try:
		db_dato = models.Datos(
			dato_fecha = func.now(),
			dato_valor = dato.dato_valor,
			estacion_id = dato.estacion_id,
		)			
		db.add(db_dato)   	
		db.commit()
		db.refresh(db_dato)			
		return db_dato
		
	except IntegrityError as e:
		raise HTTPException(status_code=500, detail="Error de integridad creando objeto Dato")
	except SQLAlchemyError as e: 
		raise HTTPException(status_code=405, detail="Error inesperado creando el objeto Dato")		

@app.get("/leer_datos/", status_code=status.HTTP_201_CREATED)  
async def leer_datos(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])],
					skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):    
	
	db_datos = db.query(
						models.Datos.id_dato,
						models.Datos.dato_fecha,
						models.Datos.dato_valor,
						models.Datos.estacion_id,
						models.Estaciones.nombre_estacion,
						models.Estaciones.codigo_estacion,
						models.Estaciones.altura_estacion,
						models.Estaciones.norte_estacion,
						models.Estaciones.sur_estacion,
					).select_from(models.Datos
					).join(models.Estaciones, models.Estaciones.id_estacion == models.Datos.estacion_id
					).order_by(models.Estaciones.nombre_estacion
					).all()	
	
	return db_datos
	
@app.get("/leer_datos_por_estacion/{id}", status_code=status.HTTP_201_CREATED)  
async def leer_datos_por_estacion(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])],
					id: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):    
	
	db_datos = db.query(
			models.Datos.id_dato,
			models.Datos.dato_fecha,
			models.Datos.dato_valor,
			models.Datos.estacion_id,
			models.Estaciones.nombre_estacion
		).select_from(models.Datos
		).join(models.Estaciones, models.Estaciones.id_estacion == models.Datos.estacion_id
		).filter(models.Estaciones.id_estacion == id
		).order_by(models.Estaciones.nombre_estacion					
		).all()	
	
	return db_datos
	
@app.delete("/eliminar_dato/{id}", status_code=status.HTTP_201_CREATED) 
async def eliminar_dato(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					id: str, db: Session = Depends(get_db)):
	
	db_dato = db.query(models.Datos
						).filter(models.Datos.id_dato == id
						).first()
	
	if db_dato is None:
		raise HTTPException(status_code=404, detail="El dato no existe en la base de datos")	
	
	db.delete(db_dato)	
	db.commit()
	return {"Result": "Dato eliminado satisfactoriamente"}
	
@app.put("/actualizar_dato/{id}", status_code=status.HTTP_201_CREATED) 
async def actualizar_dato(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])], 
				id: str, dato: schemas.Datos_UPD, db: Session = Depends(get_db)):
	
	db_dato = db.query(models.Datos).filter(models.Datos.id_dato == id).first()
	
	if db_dato is None:
		raise HTTPException(status_code=404, detail="El dato seleccionado no existe en la base de datos")
	
	db_dato.dato_valor = dato.dato_valor
	
	db.commit()
	db.refresh(db_dato)	
	
	return {"Result": "Dato actualizado satisfactoriamente"}	

@app.put("/crear_dato_faltante/", status_code=status.HTTP_201_CREATED) 
async def crear_dato_faltante(current_user: Annotated[schemas.User, Security(get_current_user, scopes=["investigador", "cliente"])], 
				dato: schemas.Datos_Faltante, db: Session = Depends(get_db)):
	
	db_dato.dato_fecha = dato.dato_fecha
	db_dato.dato_valor = dato.dato_valor
	
	db.commit()
	db.refresh(db_dato)	
	
	return {"Result": "Dato actualizado satisfactoriamente"}	

#############################
####### MODELS STUFF ########
#############################	
# , parse_dates={"fecha_dato":"%YYYY-%mm-%dd"}
@app.get("/obtener_estadisticas_estacion/{id}")
async def obtener_estadisticas_estacion(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					id: str, db: Session = Depends(get_db)):
	
	sql = db.query(
			models.Datos.dato_fecha,
			models.Datos.dato_valor
		).select_from(models.Datos
		).join(models.Estaciones, models.Estaciones.id_estacion == models.Datos.estacion_id
		).filter(models.Estaciones.id_estacion == id
		).statement
					   
	df = pd.read_sql(sql, con=engine)
	
	est = df.describe()
	
	estadistica = {
		"count": est["dato_valor"][0],
		"mean": est["dato_valor"][1],
		"std": est["dato_valor"][2],
		"min": est["dato_valor"][3],
		"25p": est["dato_valor"][4],
		"50p": est["dato_valor"][5],
		"75p": est["dato_valor"][6],
		"max": est["dato_valor"][7]	
	}
		
	return estadistica

@app.get("/obtener_estadisticas/")
async def obtener_estadisticas(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					 db: Session = Depends(get_db)):
	
	sql_estadisticas = db.query(
			func.count(models.Datos.dato_valor).label("datos_registrados"),
			func.sum(models.Datos.dato_valor).label("total_precipitaciones"),
			func.max(models.Datos.dato_valor).label("max_precipitaciones"),
			func.min(models.Datos.dato_valor).label("min_precipitaciones"),
			models.Estaciones.nombre_estacion
		).select_from(models.Datos
		).join(models.Estaciones, models.Estaciones.id_estacion == models.Datos.estacion_id
		).group_by(models.Estaciones.nombre_estacion
		).all()
					   
	#df = pd.read_sql(sql, con=engine) 	
		
	return sql_estadisticas
	
@app.get("/estacion_csv/{id}")
async def estacion_csv(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					id: str, db: Session = Depends(get_db)):
	
	sql = db.query(
			models.Datos.dato_fecha,
			models.Datos.dato_valor
		).select_from(models.Datos
		).join(models.Estaciones, models.Estaciones.id_estacion == models.Datos.estacion_id
		).filter(models.Estaciones.id_estacion == id
		).statement
					   
	df = pd.read_sql(sql, con=engine)	
	#df.to_csv("data.csv", index=False, encoding="utf-8")	
	stream = StringIO()
	df.to_csv(stream, index=False, encoding="utf-8")	
	response = StreamingResponse(iter([stream.getvalue()]),	media_type="text/csv")
	response.headers["Content-Disposition"] = "attachement; filename=export.csv"	
		
	return response
	
@app.get("/predicciones_estacion/{id}")
async def predicciones_estacion(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					id: str, db: Session = Depends(get_db)):
	
	#Cargando datos
	sql = db.query(
		models.Datos.dato_fecha,
		models.Datos.dato_valor
	).select_from(models.Datos
	).join(models.Estaciones, models.Estaciones.id_estacion == models.Datos.estacion_id
	).filter(models.Estaciones.id_estacion == id
	).statement
					   
	datos = pd.read_sql(sql, con=engine)	
	#Preparando datos
	datos["dato_fecha"] = pd.to_datetime(datos["dato_fecha"], format="%Y-%m-%d")
	datos = datos.set_index("dato_fecha")
	datos = datos.asfreq("MS", fill_value=np.nan)
	datos["dato_valor"].fillna(datos["dato_valor"].mean(), inplace=True)
	datos = datos.sort_index()
	#Preparando el clasificador	
	regressor = RandomForestRegressor(max_depth=3, n_estimators=500, random_state=123)
	forecaster = ForecasterAutoreg(regressor = regressor, lags = 20)
	forecaster.fit(y=datos["dato_valor"])
	#Realizando las predicciones
	predicciones = forecaster.predict(steps=36)
						
	return predicciones
	
#############################
####### CARGAR DATOS ########
#############################	
#from fastapi import BackgroundTasks
#metodo(bgt: BackgroundTasks, file: UploadFile = File(...))
#csvReader = csv.DictReader(codecs.iterdecode(file.file, "utf-8"))
#bgt.add_task(file.file.close())
#return list(csvReader)

def formateData(input_date):
	format = "%Y/%m/%d"	
	input_without_space = input_date.strip()
	_datetime = datetime.strptime(input_without_space, format)
	return _datetime.date()
	
def del_withe_spaces(input):	
	templ = input.lstrip()
	return templ.rstrip()
	
def formatNumber(inputN):
	if inputN < 10:
		return "0" + str(inputN)
	return str(inputN)
	
def createFecha(anno, mes, dia):
	return anno+"/"+mes+"/"+dia
	
@app.post("/cargar_dato_simple_format/")
async def cargar_dato_simple_format(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					file: UploadFile = File(...), db: Session = Depends(get_db)):
					
	csvReader = csv.DictReader(codecs.iterdecode(file.file, "utf-8"))
	estadistica = {
		"provincias_count": 0, 
		"municipios_count": 0, 
		"estaciones_count": 0, 
		"datos_count": 0
	}
	
	for rows in csvReader:
	
		provincia = del_withe_spaces(rows["Provincia"])
		municipio = del_withe_spaces(rows["Municipio"])
		estacion = del_withe_spaces(rows["Estacion"])
		fecha = del_withe_spaces(rows["Fecha"])
		valor = del_withe_spaces(rows["Valor"])
								
		db_provincia = db.query(models.Provincias).filter(models.Provincias.nombre_provincia == provincia).first()
		#Buscar si la provincia no existe		
		if db_provincia is None:
			print(provincia + ":  No existe")
			try:
				db_provincia = models.Provincias(nombre_provincia = provincia)			
				db.add(db_provincia)   	
				db.commit()
				db.refresh(db_provincia)
				estadistica["provincias_count"] += 1
				
				db_municipio = db.query(models.Municipios).filter(models.Municipios.nombre_municipio == municipio).first()
				#Buscar si el municipio existe		
				if db_municipio is None:
					print(db_provincia.nombre_provincia + " : " + municipio + " : No existe")
					try:
						db_municipio = models.Municipios(
							nombre_municipio = municipio,
							provincia_id = db_provincia.id_provincia,
						)			
						db.add(db_municipio)   	
						db.commit()
						db.refresh(db_municipio)
						estadistica["municipios_count"] += 1
						
						db_estacion = db.query(models.Estaciones).filter(models.Estaciones.nombre_estacion == estacion).first()
						#Buscar si la estacion existe	
						if db_estacion is None:
							try:
								db_estacion = models.Estaciones(
									nombre_estacion = estacion,
									municipio_id = db_municipio.id_municipio,
								)			
								db.add(db_estacion)   	
								db.commit()
								db.refresh(db_estacion)	
								estadistica["estaciones_count"] += 1
								
								try:
									db_dato = models.Datos(
										dato_fecha = formateData(fecha),
										dato_valor = valor,
										estacion_id = db_estacion.id_estacion,
									)			
									db.add(db_dato)   	
									db.commit()
									db.refresh(db_dato)
									estadistica["datos_count"] += 1
									
								except IntegrityError as e: #Para datos
									db.rollback()
									pass
								
							except SQLAlchemyError as e: #Para estacion
								pass
								
						else:
							try:
								db_dato = models.Datos(
									dato_fecha = formateData(fecha),
									dato_valor = valor,
									estacion_id = db_estacion.id_estacion,
								)			
								db.add(db_dato)   	
								db.commit()
								db.refresh(db_dato)
								estadistica["datos_count"] += 1
								
							except IntegrityError as e: #Para datos
								db.rollback()
								pass
						
					except SQLAlchemyError as e: #Para municipio
						pass
					
				else:
					db_estacion = db.query(models.Estaciones).filter(models.Estaciones.nombre_estacion == estacion).first()
					#Buscar si la estacion existe	
					if db_estacion is None:
						try:
							db_estacion = models.Estaciones(
								nombre_estacion = estacion,
								municipio_id = db_municipio.id_municipio,
							)			
							db.add(db_estacion)   	
							db.commit()
							db.refresh(db_estacion)	
							estadistica["estaciones_count"] += 1
							
							try:
								db_dato = models.Datos(
									dato_fecha = formateData(fecha),
									dato_valor = valor,
									estacion_id = db_estacion.id_estacion,
								)			
								db.add(db_dato)   	
								db.commit()
								db.refresh(db_dato)
								estadistica["datos_count"] += 1
								
							except IntegrityError as e: #Para datos
								db.rollback()
								pass
							
						except SQLAlchemyError as e: #Para estacion
							pass
					
					else:
						try:
							db_dato = models.Datos(
								dato_fecha = formateData(fecha),
								dato_valor = valor,
								estacion_id = db_estacion.id_estacion,
							)			
							db.add(db_dato)   	
							db.commit()
							db.refresh(db_dato)
							estadistica["datos_count"] += 1
							
						except IntegrityError as e: #Para datos
							db.rollback()
							pass
					
			except SQLAlchemyError as e: #Para provincia
				pass
		
		else:
			db_municipio = db.query(models.Municipios).filter(models.Municipios.nombre_municipio == municipio).first()
			#Buscar si el municipio existe		
			if db_municipio is None:
				print(db_provincia.nombre_provincia + ": Existe " + " : " + municipio + " : No existe")
				try:
					db_municipio = models.Municipios(
						nombre_municipio = municipio,
						provincia_id = db_provincia.id_provincia,
					)			
					db.add(db_municipio)   	
					db.commit()
					db.refresh(db_municipio)
					estadistica["municipios_count"] += 1
					
					db_estacion = db.query(models.Estaciones).filter(models.Estaciones.nombre_estacion == estacion).first()
					#Buscar si la estacion existe	
					if db_estacion is None:
						try:
							db_estacion = models.Estaciones(
								nombre_estacion = estacion,
								municipio_id = db_municipio.id_municipio,
							)			
							db.add(db_estacion)   	
							db.commit()
							db.refresh(db_estacion)	
							estadistica["estaciones_count"] += 1
							
							try:
								db_dato = models.Datos(
									dato_fecha = formateData(fecha),
									dato_valor = valor,
									estacion_id = db_estacion.id_estacion,
								)			
								db.add(db_dato)   	
								db.commit()
								db.refresh(db_dato)
								estadistica["datos_count"] += 1
								
							except IntegrityError as e: #Para datos
								db.rollback()
								pass
							
						except SQLAlchemyError as e: #Para estacion
							pass
							
					else:
						try:
							db_dato = models.Datos(
								dato_fecha = formateData(fecha),
								dato_valor = valor,
								estacion_id = db_estacion.id_estacion,
							)			
							db.add(db_dato)   	
							db.commit()
							db.refresh(db_dato)
							estadistica["datos_count"] += 1
							
						except IntegrityError as e: #Para datos
							db.rollback()
							pass
					
				except SQLAlchemyError as e: #Para municipio
					pass
			
			else:
				db_estacion = db.query(models.Estaciones).filter(models.Estaciones.nombre_estacion == estacion).first()
				#Buscar si la estacion existe	
				if db_estacion is None:
					try:
						db_estacion = models.Estaciones(
							nombre_estacion = estacion,
							municipio_id = db_municipio.id_municipio,
						)			
						db.add(db_estacion)   	
						db.commit()
						db.refresh(db_estacion)	
						estadistica["estaciones_count"] += 1
						
						try:
							db_dato = models.Datos(
								dato_fecha = formateData(fecha),
								dato_valor = valor,
								estacion_id = db_estacion.id_estacion,
							)			
							db.add(db_dato)   	
							db.commit()
							db.refresh(db_dato)
							estadistica["datos_count"] += 1
							
						except IntegrityError as e: #Para datos
							db.rollback()
							pass
						
					except SQLAlchemyError as e: #Para estacion
						pass
						
				else:
					try:
						db_dato = models.Datos(
							dato_fecha = formateData(fecha),
							dato_valor = valor,
							estacion_id = db_estacion.id_estacion,
						)			
						db.add(db_dato)   	
						db.commit()
						db.refresh(db_dato)
						estadistica["datos_count"] += 1
						
					except IntegrityError as e: #Para datos
						db.rollback()
						pass
		
	file.file.close()
		
	return estadistica
	
@app.post("/cargar_dato_pluviometros/")
async def cargar_dato_pluviometros(current_user: Annotated[schemas.User, Depends(get_current_active_user)],
					file: UploadFile = File(...), db: Session = Depends(get_db)):
					
	csvReader = csv.DictReader(codecs.iterdecode(file.file, "utf-8"))	
	estadistica = {
		"datos_count": 0,
		"nuevos": 0,
		"existen": 0
	}
	
	for rows in csvReader:			
		estacion = del_withe_spaces(rows["Estacion"])  #
		anno = del_withe_spaces(rows["Ano"])
		mes = del_withe_spaces(rows["IdMes"])
		
		#Precondicion, ya la estacion existe
		db_estacion = db.query(models.Estaciones).filter(models.Estaciones.nombre_estacion == estacion).first()
		
		for i in range(1, 31):
			try:
				dia = "Dia" + formatNumber(i)
				valor = del_withe_spaces(rows[dia])		
				fecha = formateData(createFecha(anno, mes, formatNumber(i)))
				fechades = formateData(createFecha(anno, mes, formatNumber(i+1)))				
				#print(createFecha(anno, mes, formatNumber(i)) + ": " + str(valor))
				
				try:
					db_dato = models.Datos(
						dato_fecha =fecha,
						dato_valor = valor,
						estacion_id = db_estacion.id_estacion,
					)			
					db.add(db_dato)   	
					db.commit()
					db.refresh(db_dato)
					estadistica["datos_count"] += 1
					estadistica["nuevos"] += 1 
					
				except IntegrityError as e: #Para datos
					db.rollback()
					pass
						
				
			except ValueError as e:
				pass
		
	return  estadistica
		
	


