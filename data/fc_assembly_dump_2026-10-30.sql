-- MySQL dump 10.13  Distrib 8.0.46, for Win64 (x86_64)
--
-- Host: localhost    Database: fc_assembly
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `fc_assembly`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `fc_assembly` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `fc_assembly`;

--
-- Table structure for table `box_positions`
--

DROP TABLE IF EXISTS `box_positions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `box_positions` (
  `settings_id` int NOT NULL,
  `box_id` int NOT NULL AUTO_INCREMENT,
  `box_type` enum('BIN','JIG') NOT NULL,
  `label` varchar(20) NOT NULL,
  `x` int NOT NULL,
  `y` int NOT NULL,
  `fill_color` char(7) DEFAULT NULL,
  `cam_x` double DEFAULT NULL,
  `cam_y` double DEFAULT NULL,
  `cam_w` double DEFAULT NULL,
  `cam_h` double DEFAULT NULL,
  PRIMARY KEY (`box_id`),
  UNIQUE KEY `uq_box` (`settings_id`,`box_type`,`label`),
  CONSTRAINT `fk_box_positions_settings` FOREIGN KEY (`settings_id`) REFERENCES `part_settings` (`settings_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `box_positions`
--

LOCK TABLES `box_positions` WRITE;
/*!40000 ALTER TABLE `box_positions` DISABLE KEYS */;
INSERT INTO `box_positions` VALUES (1,1,'BIN','BIN1',61,12,NULL,NULL,NULL,NULL,NULL),(1,2,'BIN','BIN2',231,12,NULL,NULL,NULL,NULL,NULL),(1,3,'BIN','BIN3',407,12,NULL,NULL,NULL,NULL,NULL),(1,4,'BIN','BIN4',542,12,NULL,NULL,NULL,NULL,NULL),(1,5,'BIN','BIN5',671,12,NULL,NULL,NULL,NULL,NULL),(1,6,'BIN','BIN6',821,12,NULL,NULL,NULL,NULL,NULL),(1,7,'JIG','J1',68,12,NULL,NULL,NULL,NULL,NULL),(1,8,'JIG','J2',235,12,NULL,NULL,NULL,NULL,NULL),(1,9,'JIG','J3',418,12,NULL,NULL,NULL,NULL,NULL),(1,10,'JIG','J4',550,12,NULL,NULL,NULL,NULL,NULL),(1,11,'JIG','J5',669,12,NULL,NULL,NULL,NULL,NULL),(1,12,'JIG','J6',823,12,NULL,NULL,NULL,NULL,NULL),(2,13,'BIN','BIN1',41,12,'#FF3030',NULL,NULL,NULL,NULL),(2,14,'BIN','BIN2',442,12,'#00E676',NULL,NULL,NULL,NULL),(2,15,'BIN','BIN3',562,12,'#2979FF',NULL,NULL,NULL,NULL),(2,16,'BIN','BIN4',776,12,'#FFEA00',NULL,NULL,NULL,NULL),(2,17,'BIN','BIN5',948,12,'#D500F9',NULL,NULL,NULL,NULL),(2,18,'JIG','J1',61,12,'#FFEA00',NULL,NULL,NULL,NULL),(2,19,'JIG','J2',442,12,NULL,NULL,NULL,NULL,NULL),(2,20,'JIG','J3',562,12,NULL,NULL,NULL,NULL,NULL),(2,21,'JIG','J4',682,12,NULL,NULL,NULL,NULL,NULL),(2,22,'JIG','J5',802,12,NULL,NULL,NULL,NULL,NULL);
/*!40000 ALTER TABLE `box_positions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `part_settings`
--

DROP TABLE IF EXISTS `part_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `part_settings` (
  `settings_id` int NOT NULL AUTO_INCREMENT,
  `part_number` varchar(100) NOT NULL,
  `model_number` varchar(100) NOT NULL,
  `customer_name` varchar(150) NOT NULL,
  `vendor_code` varchar(100) NOT NULL,
  `bin_count` tinyint unsigned NOT NULL,
  `jig_count` tinyint unsigned NOT NULL,
  `row_width` smallint unsigned DEFAULT NULL,
  `updated_at` timestamp(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`settings_id`),
  UNIQUE KEY `uq_part_number` (`part_number`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `part_settings`
--

LOCK TABLES `part_settings` WRITE;
/*!40000 ALTER TABLE `part_settings` DISABLE KEYS */;
INSERT INTO `part_settings` VALUES (1,'p001','M001','LEKA','V001',6,6,1204,'2026-10-24 13:40:15.465556'),(2,'p002','M002','VENKAT','V002',5,5,1204,'2026-10-26 11:02:47.513019');
/*!40000 ALTER TABLE `part_settings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping events for database 'fc_assembly'
--

--
-- Dumping routines for database 'fc_assembly'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-30 18:53:54
