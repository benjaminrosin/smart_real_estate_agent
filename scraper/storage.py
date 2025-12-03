"""
Data storage module for saving scraped property listings
"""
import pandas as pd
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import json


class DataStorage:
    """Handle storage of scraped property data"""
    
    def __init__(self, output_dir: Path):
        """
        Initialize storage handler
        
        Args:
            output_dir: Directory to save output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
    
    def save_to_csv(self, data: List[Dict], filename: str = None) -> Path:
        """
        Save data to CSV file
        
        Args:
            data: List of property dictionaries
            filename: Optional custom filename (default: timestamped)
            
        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"yad2_rentals_{timestamp}.csv"
        
        filepath = self.output_dir / filename
        
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        print(f"Saved {len(data)} listings to {filepath}")
        return filepath
    
    def save_to_json(self, data: List[Dict], filename: str = None) -> Path:
        """
        Save data to JSON file
        
        Args:
            data: List of property dictionaries
            filename: Optional custom filename (default: timestamped)
            
        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"yad2_rentals_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Saved {len(data)} listings to {filepath}")
        return filepath
    
    def save_both(self, data: List[Dict], base_filename: str = None) -> tuple:
        """
        Save data to both CSV and JSON formats
        
        Args:
            data: List of property dictionaries
            base_filename: Optional base filename without extension
            
        Returns:
            Tuple of (csv_path, json_path)
        """
        if not base_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"yad2_rentals_{timestamp}"
        
        csv_path = self.save_to_csv(data, f"{base_filename}.csv")
        json_path = self.save_to_json(data, f"{base_filename}.json")
        
        return csv_path, json_path
    
    def load_csv(self, filepath: Path) -> pd.DataFrame:
        """
        Load data from CSV file
        
        Args:
            filepath: Path to CSV file
            
        Returns:
            DataFrame with loaded data
        """
        return pd.read_csv(filepath, encoding='utf-8-sig')
    
    def load_json(self, filepath: Path) -> List[Dict]:
        """
        Load data from JSON file
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            List of property dictionaries
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
