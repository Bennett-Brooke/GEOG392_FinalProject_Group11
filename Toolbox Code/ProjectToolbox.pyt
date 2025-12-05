# -*- coding: utf-8 -*-
import arcpy
import os

class Toolbox(object):
    def __init__(self):
        self.label = "ProjectToolbox"
        self.alias = "ProjectToolbox"
        self.tools = [ExtractCountyData]

class ExtractCountyData(object):
    def __init__(self):
        self.label = "Extract County Population & Grocery Stores"
        self.description = "Extracts Block Groups and Grocery Stores, identifies food deserts, and outputs full candidates, top 3, and top 1 candidate locations."

    def getParameterInfo(self):
        county_param = arcpy.Parameter(
            displayName="County Name",
            name="county_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        return [county_param]

    def execute(self, parameters, messages):
        county_name = parameters[0].valueAsText
        messages.addMessage("🔍 Searching for layers...")

        # ----------------------------------------------------
        # Output geodatabase setup
        # ----------------------------------------------------
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        project_folder = os.path.dirname(aprx.filePath)
        output_folder = os.path.join(project_folder, "County_Outputs")
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        gdb_name = f"{county_name.replace(' ', '_')}_Output.gdb"
        output_gdb = os.path.join(output_folder, gdb_name)
        if not arcpy.Exists(output_gdb):
            arcpy.management.CreateFileGDB(output_folder, gdb_name)
            messages.addMessage(f"📂 Created new output geodatabase: {output_gdb}")
        else:
            messages.addMessage(f"📂 Using existing geodatabase: {output_gdb}")

        arcpy.env.workspace = output_gdb
        arcpy.env.overwriteOutput = True

        # ----------------------------------------------------
        # Layers
        # ----------------------------------------------------
        map_obj = aprx.activeMap
        block_group_layer = None
        for lyr in map_obj.listLayers():
            if lyr.name == "USA 2020 Census Population Characteristics":
                for sub in lyr.listLayers():
                    if sub.name == "Block Group":
                        block_group_layer = sub
        if block_group_layer is None:
            raise arcpy.ExecuteError("❌ Block Group layer not found.")

        grocery_layer = None
        for lyr in map_obj.listLayers():
            if lyr.name == "GroceryStores":
                grocery_layer = lyr
        if grocery_layer is None:
            raise arcpy.ExecuteError("❌ GroceryStores layer not found.")

        counties = [lyr for lyr in map_obj.listLayers() if lyr.name == "County"]
        if not counties:
            raise arcpy.ExecuteError("❌ County layer not found.")
        county_layer = counties[0]
        sql = f"NAME = '{county_name}'"
        arcpy.management.MakeFeatureLayer(county_layer, "county_lyr", sql)

        # ----------------------------------------------------
        # Clip Block Groups & Grocery Stores
        # ----------------------------------------------------
        bg_output = os.path.join(output_gdb, f"BlockGroups_{county_name.replace(' ', '_')}")
        arcpy.analysis.Clip(block_group_layer, "county_lyr", bg_output)

        store_output = os.path.join(output_gdb, f"GroceryStores_{county_name.replace(' ', '_')}")
        arcpy.analysis.Clip(grocery_layer, "county_lyr", store_output)

        # ----------------------------------------------------
        # Create 1.6 km buffers & food deserts
        # ----------------------------------------------------
        buffer_output = os.path.join(output_gdb, f"GroceryStores_Buffer_{county_name.replace(' ', '_')}")
        arcpy.analysis.Buffer(store_output, buffer_output, "1600 Meters", dissolve_option="NONE")

        food_desert_output = os.path.join(output_gdb, f"FoodDeserts_{county_name.replace(' ', '_')}")
        arcpy.analysis.Erase(county_layer, buffer_output, food_desert_output)

        # ----------------------------------------------------
        # Clip block groups to food desert
        # ----------------------------------------------------
        fg_bg_clip = os.path.join(output_gdb, f"BlockGroups_FoodDesert_{county_name.replace(' ', '_')}")
        arcpy.analysis.Clip(bg_output, food_desert_output, fg_bg_clip)
        if int(arcpy.management.GetCount(fg_bg_clip)[0]) == 0:
            messages.addWarningMessage("⚠ No block groups in the food desert area.")
            return

        # ----------------------------------------------------
        # Create centroids
        # ----------------------------------------------------
        centroids_output = os.path.join(output_gdb, f"FoodDesert_Centroids_{county_name.replace(' ', '_')}")
        arcpy.management.FeatureToPoint(fg_bg_clip, centroids_output, "INSIDE")

        # ----------------------------------------------------
        # Population density
        # ----------------------------------------------------
        if "POP_DENSITY" not in [f.name for f in arcpy.ListFields(centroids_output)]:
            arcpy.management.AddField(centroids_output, "POP_DENSITY", "DOUBLE")
        arcpy.management.CalculateField(
            centroids_output,
            "POP_DENSITY",
            "(!P0010001! if !P0010001! else 0) / (!SHAPE.area@SQUAREKILOMETERS! if !SHAPE.area@SQUAREKILOMETERS! else 1)",
            "PYTHON3"
        )

        # ----------------------------------------------------
        # Distance to nearest grocery store
        # ----------------------------------------------------
        near_table = os.path.join(output_gdb, "NearTable_FoodDesert")
        arcpy.analysis.GenerateNearTable(centroids_output, store_output, near_table, location="LOCATION", angle="NO_ANGLE", closest="ALL")
        arcpy.management.JoinField(centroids_output, "OBJECTID", near_table, "IN_FID", ["NEAR_DIST"])

        # ----------------------------------------------------
        # Score (Joel Arndt)
        #
        # Score will be calculated by multiplying the population density by the distance from the
        # nearest grocery store.
        # ----------------------------------------------------
        if "SCORE" not in [f.name for f in arcpy.ListFields(centroids_output)]: # Check if field hasn't been created yet
            arcpy.management.AddField(centroids_output, "SCORE", "DOUBLE") # If not, create field
        arcpy.management.CalculateField( # Calculate score field
            centroids_output, # Feature to be edited
            "SCORE", # Field to be calculated
            "(!NEAR_DIST! if !NEAR_DIST! else 0) * (!POP_DENSITY! if !POP_DENSITY! else 0)", # If both fields exist, multiply. If not, return 0.
            "PYTHON3" # Make sure ArcPro knows which language to check for.
        )

        # ----------------------------------------------------
        # Selection (Joel Arndt)
        #
        # Centroids will be selected for export if they are outside of the buffer distance
        # ----------------------------------------------------
        centroids_to_export = arcpy.management.SelectLayerByLocation(centroids_output, "INTERSECT", food_desert_output)

        # ----------------------------------------------------
        # Export Candidates (Yuan Niu & Clay Davlin)
        # ----------------------------------------------------
        messages.addMessage("📤 Exporting candidates...")

        # 1. Export ALL candidates in the food desert (Full List)
        # ----------------------------------------------------
        # Define output name for full candidates
        full_candidates_output = os.path.join(output_gdb, f"Candidates_Full_{county_name.replace(' ', '_')}")
        
        # Copy the selected features (centroids_to_export) to a new feature class
        arcpy.management.CopyFeatures(centroids_to_export, full_candidates_output)
        messages.addMessage(f"✅ Full candidate list exported: {full_candidates_output}")

        # 2. Select and Export Top 3 Candidates based on SCORE
        # ----------------------------------------------------
        # We need to sort the data by SCORE in descending order to get the highest scores.
        # ArcPy doesn't have a simple "Select Top N" tool, so we Sort -> Get IDs -> Select.
        
        # Step A: Use Sort tool to create a temporary sorted feature class
        sorted_candidates = os.path.join(output_gdb, "Sorted_Candidates_Temp")
        # Sort by SCORE descending (Highest score first)
        arcpy.management.Sort(full_candidates_output, sorted_candidates, [["SCORE", "DESCENDING"]])
        
        # Step B: Find the Object IDs (OIDs) of the top 3 rows
        top_3_oids = []
        # Use a SearchCursor to read the first 3 rows of the sorted data
        with arcpy.da.SearchCursor(sorted_candidates, ["OID@"]) as cursor:
            for i, row in enumerate(cursor):
                if i < 3:
                    top_3_oids.append(row[0])
                else:
                    break # Stop after getting 3
        
        # Step C: Export Top 3
        if top_3_oids:
            # Create a SQL query to select these IDs: e.g., "OBJECTID IN (1, 5, 12)"
            oid_string = ",".join(map(str, top_3_oids))
            sql_top3 = f"OBJECTID IN ({oid_string})"
            
            # Create output path
            top_3_output = os.path.join(output_gdb, f"Candidates_Top3_{county_name.replace(' ', '_')}")
            
            # Make a temporary layer with the selection applied
            arcpy.management.MakeFeatureLayer(sorted_candidates, "top_3_lyr", sql_top3)
            # Save selection to GDB
            arcpy.management.CopyFeatures("top_3_lyr", top_3_output)
            messages.addMessage(f"✅ Top 3 candidates exported: {top_3_output}")
        else:
            messages.addWarningMessage("⚠ No candidates found for Top 3 selection.")

        # 3. Select and Export Top 1 Candidate
        # ----------------------------------------------------
        top_1_output = os.path.join(output_gdb, f"Candidate_Top1_{county_name.replace(' ', '_')}")
        
        if top_3_oids:
            # The first OID in our sorted list is the Top 1 (Highest Score)
            top_1_oid = top_3_oids[0]
            sql_top1 = f"OBJECTID = {top_1_oid}"
            
            arcpy.management.MakeFeatureLayer(sorted_candidates, "top_1_lyr", sql_top1)
            arcpy.management.CopyFeatures("top_1_lyr", top_1_output)
            messages.addMessage(f"✅ Top 1 candidate exported: {top_1_output}")
        else:
             messages.addWarningMessage("⚠ No candidates found for Top 1 selection.")
        
        # ----------------------------------------------------
        # Cleanup
        # ----------------------------------------------------
        # Clean up temporary sorted file to keep GDB clean
        if arcpy.Exists(sorted_candidates):
            arcpy.management.Delete(sorted_candidates)

        return