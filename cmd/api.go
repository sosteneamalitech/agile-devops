package main

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"golang.org/x/crypto/bcrypt"
)

type User struct {
	ID       int    `json:"id"`
	Name     string `json:"name"`
	Email    string `json:"email"`
	Password string `json:"-"`
}

type RegisterInput struct {
	Name     string `json:"name" binding:"required"`
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=6"`
}

var users=[]User{}
var nextID = 1

func main() {
	r := gin.Default()

	r.GET("/users", func(c *gin.Context) {
		c.JSON(http.StatusOK, users)
	})

	r.POST("/users", func(c *gin.Context) {
		var input RegisterInput

		if err := c.ShouldBindJSON(&input); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid or missing data: " + err.Error()})
			return
		}

		for _, u := range users {
			if u.Email == input.Email {
				c.JSON(http.StatusConflict, gin.H{"error": "An account with this email already exists"})
				return
			}
		}

		hashedPassword, err := bcrypt.GenerateFromPassword([]byte(input.Password), bcrypt.DefaultCost)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to process password"})
			return
		}

		newUser := User{
			ID:       nextID,
			Name:     input.Name,
			Email:    input.Email,
			Password: string(hashedPassword),
		}

		users = append(users, newUser)
		nextID++

		c.JSON(http.StatusCreated, gin.H{
			"id":    newUser.ID,
			"email": newUser.Email,
			"name":  newUser.Name,
		})
	})

	r.Run(":8080")
}
