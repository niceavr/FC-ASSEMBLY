//Count and print the factors of the given number
#include<stdio.h>
int main()
{
	int n,i,count;
	printf("Enter n value\n");
	scanf("%d",&n);
	i=1;
	count=0;
	while(i<=n)
	{
		if(n%i==0)
		   count=count+1;
		i=i+1;
	}
	printf("number of factors are %d\n",count);
	if(count==2)
	  printf("Prime number");
	else
	   printf("Not a prime number");
}



